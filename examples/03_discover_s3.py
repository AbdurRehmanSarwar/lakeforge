"""Discover partitions and a manifest from a (fake) S3 bucket.

NOTE: This example uses `moto` (the AWS mocking library) to stand up an
in-memory, fake S3 bucket so the demo is fully self-contained and never touches
real AWS. No credentials, network access, or real buckets are required.

It populates the fake bucket with Hive-style partitioned object keys, then uses:

* :func:`lakeforge.discovery.discover_partitions` to reconstruct the distinct
  partitions present under a prefix, and
* :func:`lakeforge.discovery.discover_manifest` to additionally collect the
  object keys belonging to each partition into a :class:`lakeforge.Manifest`.

The moto-created boto3 client is passed explicitly via the ``client=`` argument
so discovery talks to the fake S3 instead of constructing a real one.

Run it with::

    python examples/03_discover_s3.py
"""

from __future__ import annotations

import boto3
from moto import mock_aws

from lakeforge import schema
from lakeforge.discovery import discover_manifest, discover_partitions

BUCKET = "demo-data-lake"
PREFIX = "events/"

# Hive-style object keys to seed the fake bucket with. Two of these share a
# partition (year=2024/month=1/region=us) to show de-duplication and manifest
# file collection. The last key has no partition path and should be skipped.
SAMPLE_KEYS = [
    "events/year=2024/month=1/region=us/part-0000.parquet",
    "events/year=2024/month=1/region=us/part-0001.parquet",
    "events/year=2024/month=1/region=eu/part-0000.parquet",
    "events/year=2024/month=2/region=us/part-0000.parquet",
    "events/year=2023/month=12/region=apac/part-0000.parquet",
    "events/_SUCCESS",  # no partition path -> skipped by non-strict discovery
]


@mock_aws
def main() -> None:
    part_schema = schema(("year", "int"), ("month", "int"), "region")

    # Stand up the fake bucket and upload the sample objects.
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket=BUCKET)
    for key in SAMPLE_KEYS:
        s3.put_object(Bucket=BUCKET, Key=key, Body=b"")
    print(f"Seeded s3://{BUCKET}/ with {len(SAMPLE_KEYS)} objects.\n")

    # discover_partitions: distinct partitions, de-duplicated, first-seen order.
    partitions = discover_partitions(BUCKET, PREFIX, part_schema, client=s3)
    print(f"discover_partitions found {len(partitions)} distinct partitions:")
    for partition in partitions:
        print(f"  {partition.path()}  ->  values={partition.to_dict()}")

    # discover_manifest: partitions plus the file URIs under each one.
    manifest = discover_manifest(BUCKET, PREFIX, part_schema, client=s3)
    print(
        f"\ndiscover_manifest built {len(manifest.entries)} entries "
        f"covering {manifest.total_files} files:"
    )
    for entry in manifest.entries:
        print(f"  {entry.partition.path()}  ({len(entry.files)} file(s))")
        for uri in entry.files:
            print(f"    - {uri}")

    print("\nManifest as lakeforge JSON:")
    print(manifest.to_json())


if __name__ == "__main__":
    main()
