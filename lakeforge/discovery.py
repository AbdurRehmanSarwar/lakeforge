"""S3 partition discovery (optional, requires boto3).

Scan an S3 prefix and reconstruct the set of Hive-style partitions present,
parsed against a :class:`~lakeforge.schema.PartitionSchema`. Optionally collect
the object keys under each partition into a :class:`~lakeforge.manifest.Manifest`.

``boto3`` is imported lazily so the rest of lakeforge has no AWS dependency.
Install the extra with ``pip install lakeforge[aws]``.
"""

from __future__ import annotations

from typing import Any

from .errors import DiscoveryError, PartitionParseError, SchemaError
from .manifest import Manifest
from .partition import Partition
from .schema import PartitionSchema


def _s3_client(client: Any | None) -> Any:
    if client is not None:
        return client
    try:
        import boto3
    except ImportError as exc:  # pragma: no cover - exercised via monkeypatch in tests
        raise DiscoveryError(
            "boto3 is required for S3 discovery; install with `pip install lakeforge[aws]`"
        ) from exc
    return boto3.client("s3")


def _iter_keys(client: Any, bucket: str, prefix: str) -> Any:
    """Yield every object key under ``prefix`` using a paginator."""
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            yield obj["Key"]


def discover_partitions(
    bucket: str,
    prefix: str,
    schema: PartitionSchema,
    *,
    client: Any | None = None,
    strict: bool = False,
) -> list[Partition]:
    """Discover the distinct partitions present under ``s3://bucket/prefix``.

    Each object key is parsed against ``schema``; keys that do not contain a
    full partition path *or* whose segment values cannot be coerced to the
    declared types are skipped (or, if ``strict`` is true, the parse error —
    :class:`~lakeforge.errors.PartitionParseError` or
    :class:`~lakeforge.errors.SchemaError` — propagates). The result is
    de-duplicated and returned in first-seen order.
    """
    s3 = _s3_client(client)
    seen: dict[str, Partition] = {}
    for key in _iter_keys(s3, bucket, prefix):
        try:
            partition = Partition.parse(key, schema)
        except (PartitionParseError, SchemaError):
            if strict:
                raise
            continue
        seen.setdefault(partition.path(), partition)
    return list(seen.values())


def discover_manifest(
    bucket: str,
    prefix: str,
    schema: PartitionSchema,
    *,
    client: Any | None = None,
    strict: bool = False,
) -> Manifest:
    """Discover partitions *and* collect their object keys into a manifest.

    File URIs are recorded as ``s3://bucket/key``.
    """
    s3 = _s3_client(client)
    manifest = Manifest(schema)
    for key in _iter_keys(s3, bucket, prefix):
        try:
            partition = Partition.parse(key, schema)
        except (PartitionParseError, SchemaError):
            if strict:
                raise
            continue
        manifest.add(partition, f"s3://{bucket}/{key}")
    return manifest


__all__ = ["discover_partitions", "discover_manifest"]
