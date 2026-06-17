"""Tests for :mod:`lakeforge.discovery`.

Uses ``moto`` to mock S3. The installed moto is version 5+, which exposes
``from moto import mock_aws``.
"""

from __future__ import annotations

import builtins

import boto3
import pytest
from moto import mock_aws

import lakeforge.discovery as discovery
from lakeforge.discovery import discover_manifest, discover_partitions
from lakeforge.errors import DiscoveryError, PartitionParseError
from lakeforge.manifest import Manifest
from lakeforge.partition import Partition
from lakeforge.schema import PartitionSchema

BUCKET = "test-lake"
PREFIX = "data/"

# Schema matching keys like data/year=2024/month=1/region=us/part-0.parquet
SCHEMA = PartitionSchema.of(("year", "int"), ("month", "int"), ("region", "string"))


@pytest.fixture(autouse=True)
def _aws_credentials(monkeypatch):
    """Set dummy AWS credentials so boto3/moto never touches real AWS."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


# Keys laid out across several partitions, each with multiple files. The list
# order here is the order they are inserted; moto/list_objects_v2 returns keys
# in lexicographic order, so first-seen order is the sorted key order.
PARTITION_KEYS = [
    # year=2024/month=1/region=us  -> 3 files
    "data/year=2024/month=1/region=us/part-0.parquet",
    "data/year=2024/month=1/region=us/part-1.parquet",
    "data/year=2024/month=1/region=us/part-2.parquet",
    # year=2024/month=1/region=eu  -> 2 files
    "data/year=2024/month=1/region=eu/part-0.parquet",
    "data/year=2024/month=1/region=eu/part-1.parquet",
    # year=2024/month=2/region=us  -> 2 files
    "data/year=2024/month=2/region=us/part-0.parquet",
    "data/year=2024/month=2/region=us/part-1.parquet",
    # year=2025/month=12/region=us -> 1 file
    "data/year=2025/month=12/region=us/part-0.parquet",
]


def _make_client():
    """Create an S3 client (caller must be inside a mock_aws context)."""
    return boto3.client("s3", region_name="us-east-1")


def _put_objects(client, keys):
    client.create_bucket(Bucket=BUCKET)
    for key in keys:
        client.put_object(Bucket=BUCKET, Key=key, Body=b"x")


def _path_set(partitions):
    return {p.path() for p in partitions}


@mock_aws
def test_discover_partitions_dedups_and_returns_distinct():
    client = _make_client()
    _put_objects(client, PARTITION_KEYS)

    parts = discover_partitions(BUCKET, PREFIX, SCHEMA, client=client)

    # Four distinct partitions across the eight keys.
    assert len(parts) == 4
    assert all(isinstance(p, Partition) for p in parts)
    assert _path_set(parts) == {
        "year=2024/month=1/region=us",
        "year=2024/month=1/region=eu",
        "year=2024/month=2/region=us",
        "year=2025/month=12/region=us",
    }


@mock_aws
def test_discover_partitions_preserves_first_seen_order():
    client = _make_client()
    _put_objects(client, PARTITION_KEYS)

    parts = discover_partitions(BUCKET, PREFIX, SCHEMA, client=client)

    # list_objects_v2 yields keys lexicographically. First-seen order of the
    # distinct partition paths follows that key order.
    expected_order = [
        "year=2024/month=1/region=eu",
        "year=2024/month=1/region=us",
        "year=2024/month=2/region=us",
        "year=2025/month=12/region=us",
    ]
    assert [p.path() for p in parts] == expected_order


@mock_aws
def test_discover_partitions_values_are_typed():
    client = _make_client()
    _put_objects(client, ["data/year=2024/month=1/region=us/part-0.parquet"])

    parts = discover_partitions(BUCKET, PREFIX, SCHEMA, client=client)

    assert len(parts) == 1
    values = parts[0].to_dict()
    assert values == {"year": 2024, "month": 1, "region": "us"}
    assert isinstance(values["year"], int)
    assert isinstance(values["month"], int)
    assert isinstance(values["region"], str)


@mock_aws
def test_discover_partitions_dedups_equivalent_int_values():
    """month=01 and month=1 parse to the same int and collapse to one path."""
    client = _make_client()
    _put_objects(
        client,
        [
            "data/year=2024/month=1/region=us/part-0.parquet",
            "data/year=2024/month=01/region=us/part-1.parquet",
        ],
    )

    parts = discover_partitions(BUCKET, PREFIX, SCHEMA, client=client)

    assert len(parts) == 1
    assert parts[0].path() == "year=2024/month=1/region=us"


@mock_aws
def test_discover_manifest_records_s3_uris_per_partition():
    client = _make_client()
    _put_objects(client, PARTITION_KEYS)

    manifest = discover_manifest(BUCKET, PREFIX, SCHEMA, client=client)

    assert isinstance(manifest, Manifest)
    assert manifest.schema is SCHEMA
    # One entry per distinct partition.
    assert len(manifest.entries) == 4
    # Every key recorded exactly once, all as s3://bucket/key URIs.
    assert manifest.total_files == len(PARTITION_KEYS)
    expected_uris = {f"s3://{BUCKET}/{key}" for key in PARTITION_KEYS}
    assert set(manifest.all_files()) == expected_uris
    assert all(uri.startswith(f"s3://{BUCKET}/") for uri in manifest.all_files())

    # Files grouped under the right partition.
    by_path = {entry.partition.path(): entry for entry in manifest.entries}
    assert sorted(by_path["year=2024/month=1/region=us"].files) == [
        f"s3://{BUCKET}/data/year=2024/month=1/region=us/part-0.parquet",
        f"s3://{BUCKET}/data/year=2024/month=1/region=us/part-1.parquet",
        f"s3://{BUCKET}/data/year=2024/month=1/region=us/part-2.parquet",
    ]
    assert len(by_path["year=2024/month=1/region=eu"].files) == 2
    assert len(by_path["year=2024/month=2/region=us"].files) == 2
    assert len(by_path["year=2025/month=12/region=us"].files) == 1


@mock_aws
def test_discover_manifest_empty_prefix_is_empty():
    client = _make_client()
    client.create_bucket(Bucket=BUCKET)

    manifest = discover_manifest(BUCKET, PREFIX, SCHEMA, client=client)

    assert isinstance(manifest, Manifest)
    assert manifest.entries == []
    assert manifest.total_files == 0


@mock_aws
def test_prefix_scopes_the_scan():
    client = _make_client()
    _put_objects(
        client,
        PARTITION_KEYS
        + ["other/year=1999/month=1/region=zz/part-0.parquet"],
    )

    parts = discover_partitions(BUCKET, PREFIX, SCHEMA, client=client)

    # The "other/" key is outside the "data/" prefix and is not scanned.
    assert "year=1999/month=1/region=zz" not in _path_set(parts)
    assert len(parts) == 4


@mock_aws
def test_missing_partition_columns_skipped_when_not_strict():
    client = _make_client()
    _put_objects(
        client,
        [
            # Good key.
            "data/year=2024/month=1/region=us/part-0.parquet",
            # Missing the region column -> unparsable against the schema.
            "data/year=2024/month=2/part-0.parquet",
            # Missing month and region.
            "data/year=2024/part-0.parquet",
        ],
    )

    parts = discover_partitions(BUCKET, PREFIX, SCHEMA, client=client, strict=False)

    assert len(parts) == 1
    assert parts[0].path() == "year=2024/month=1/region=us"


@mock_aws
def test_missing_partition_columns_raises_when_strict():
    client = _make_client()
    _put_objects(
        client,
        [
            "data/year=2024/month=1/region=us/part-0.parquet",
            "data/year=2024/month=2/part-0.parquet",  # missing region
        ],
    )

    with pytest.raises(PartitionParseError):
        discover_partitions(BUCKET, PREFIX, SCHEMA, client=client, strict=True)


@mock_aws
def test_manifest_missing_columns_skipped_when_not_strict():
    client = _make_client()
    _put_objects(
        client,
        [
            "data/year=2024/month=1/region=us/part-0.parquet",
            "data/year=2024/region=us/part-0.parquet",  # missing month
        ],
    )

    manifest = discover_manifest(BUCKET, PREFIX, SCHEMA, client=client, strict=False)

    assert len(manifest.entries) == 1
    assert manifest.total_files == 1
    assert manifest.all_files() == [
        f"s3://{BUCKET}/data/year=2024/month=1/region=us/part-0.parquet"
    ]


@mock_aws
def test_manifest_missing_columns_raises_when_strict():
    client = _make_client()
    _put_objects(
        client,
        ["data/year=2024/region=us/part-0.parquet"],  # missing month
    )

    with pytest.raises(PartitionParseError):
        discover_manifest(BUCKET, PREFIX, SCHEMA, client=client, strict=True)


def test_missing_boto3_raises_discovery_error(monkeypatch):
    """When boto3 cannot be imported, _s3_client raises DiscoveryError.

    We force the lazy ``import boto3`` inside ``_s3_client`` to fail by
    patching ``builtins.__import__`` to raise ImportError for boto3.
    """
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "boto3" or name.startswith("boto3."):
            raise ImportError("No module named 'boto3'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(DiscoveryError) as excinfo:
        # client=None forces the lazy boto3 import path.
        discovery._s3_client(None)

    assert "boto3" in str(excinfo.value)


def test_missing_boto3_propagates_through_discover_partitions(monkeypatch):
    """The DiscoveryError surfaces through the public discover_* entry point."""
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "boto3" or name.startswith("boto3."):
            raise ImportError("No module named 'boto3'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(DiscoveryError):
        # No client passed -> tries to build one via boto3 -> fails.
        discover_partitions(BUCKET, PREFIX, SCHEMA)


def test_s3_client_returns_passed_client_unchanged():
    sentinel = object()
    assert discovery._s3_client(sentinel) is sentinel
