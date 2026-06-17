"""Regression tests for the security/robustness hardening pass.

Each test here pins a behaviour that was added in response to an adversarial
code review: SQL escaping in DDL, identifier validation, numeric-type guards,
the ``Partition.of`` parameter-name collision, and discovery's handling of keys
whose values cannot be coerced to the declared types.
"""

from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from lakeforge import Partition, PartitionSchema, schema
from lakeforge.errors import LakeForgeError, SchemaError
from lakeforge.glue import (
    add_partition_ddl,
    create_table_ddl,
    msck_repair,
    projection_properties,
)

# --- TBLPROPERTIES single-quote escaping --------------------------------------


def test_table_properties_escape_single_quotes_in_values():
    sch = schema(("year", "int"))
    ddl = create_table_ddl(
        "events",
        {"id": "bigint"},
        sch,
        "s3://b/events",
        table_properties={"comment": "John's data"},
    )
    # The apostrophe is doubled, so the literal stays balanced.
    assert "'comment'='John''s data'" in ddl
    assert "John's data'" not in ddl.replace("John''s data", "")


def test_table_properties_escape_single_quotes_in_keys():
    sch = schema(("year", "int"))
    ddl = create_table_ddl(
        "events", {"id": "bigint"}, sch, "s3://b/events", table_properties={"o'k": "v"}
    )
    assert "'o''k'='v'" in ddl


# --- Identifier validation ----------------------------------------------------


@pytest.mark.parametrize("bad", ["events; DROP TABLE x", "has space", "1leading", "two.parts", ""])
def test_invalid_table_name_rejected(bad):
    p = Partition.of(schema(("year", "int")), year=2024)
    with pytest.raises(LakeForgeError):
        add_partition_ddl(bad, p, "s3://b/e")


def test_invalid_database_name_rejected():
    p = Partition.of(schema(("year", "int")), year=2024)
    with pytest.raises(LakeForgeError):
        add_partition_ddl("events", p, "s3://b/e", database="bad-db")


def test_invalid_body_column_name_rejected():
    with pytest.raises(LakeForgeError):
        create_table_ddl("t", {"bad col": "string"}, schema(("year", "int")), "s3://b/t")


def test_invalid_partition_column_name_rejected():
    # A schema can hold any non-empty name, but DDL emission must reject unsafe ones.
    sch = PartitionSchema.of("ok", "bad;name")
    p = Partition(dict.fromkeys(sch.names, "v"), sch)
    with pytest.raises(LakeForgeError):
        add_partition_ddl("t", p, "s3://b/t")


def test_msck_repair_validates_table():
    with pytest.raises(LakeForgeError):
        msck_repair("t; DROP TABLE x")


def test_valid_identifiers_pass_through():
    sch = schema(("year", "int"), "region")
    p = Partition.of(sch, year=2024, region="us")
    ddl = add_partition_ddl("daily_events", p, "s3://b/e", database="analytics_v2")
    assert ddl.startswith("ALTER TABLE analytics_v2.daily_events ADD")


# --- Numeric guard on unquoted literals ---------------------------------------


class _Evil:
    def __str__(self) -> str:
        return "2024 OR 1=1"


def test_int_column_rejects_non_numeric_native_value():
    sch = schema(("year", "int"))
    # Bypass coerce()'s str-parsing by injecting a native non-numeric object.
    p = Partition({"year": _Evil()}, sch)
    with pytest.raises(SchemaError):
        add_partition_ddl("t", p, "s3://b/t")


def test_bool_is_not_accepted_as_int_literal():
    sch = schema(("n", "int"))
    p = Partition({"n": True}, sch)
    with pytest.raises(SchemaError):
        add_partition_ddl("t", p, "s3://b/t")


def test_double_column_accepts_int_value():
    sch = schema(("ratio", "double"))
    p = Partition({"ratio": 5}, sch)
    ddl = add_partition_ddl("t", p, "s3://b/t")
    assert "PARTITION (ratio=5)" in ddl


# --- Timestamp projection format matches path rendering -----------------------


def test_timestamp_projection_format_matches_path_separator():
    from datetime import datetime

    sch = schema(("ts", "timestamp"))
    rendered = Partition({"ts": datetime(2024, 1, 5, 13, 30)}, sch).path()
    props = projection_properties(
        sch, "s3://b/${ts}", ranges={"ts": ("2024-01-01T00:00:00", "NOW")}
    )
    # path() uses a 'T' separator; the projection format must agree.
    assert rendered == "ts=2024-01-05T13:30:00"
    assert props["projection.ts.format"] == "yyyy-MM-dd'T'HH:mm:ss"


# --- Partition.of parameter-name collision ------------------------------------


def test_partition_of_allows_column_named_schema():
    sch = PartitionSchema.of("schema", "region")
    p = Partition.of(sch, schema="prod", region="us")
    assert p.to_dict() == {"schema": "prod", "region": "us"}
    assert p.path() == "schema=prod/region=us"


# --- Discovery tolerates malformed typed values -------------------------------


SCHEMA = PartitionSchema.of(("year", "int"), ("region", "string"))


@pytest.fixture(autouse=True)
def _aws_credentials(monkeypatch):
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(key, "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


@mock_aws
def test_discovery_skips_unparseable_value_when_not_strict():
    from lakeforge.discovery import discover_partitions

    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="lake")
    client.put_object(Bucket="lake", Key="d/year=2024/region=us/f.parquet", Body=b"x")
    client.put_object(Bucket="lake", Key="d/year=NOTINT/region=eu/f.parquet", Body=b"x")

    parts = discover_partitions("lake", "d/", SCHEMA, client=client)
    # The malformed year=NOTINT key is skipped, not fatal.
    assert {p.path() for p in parts} == {"year=2024/region=us"}


@mock_aws
def test_discovery_strict_raises_on_unparseable_value():
    from lakeforge.discovery import discover_partitions

    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="lake")
    client.put_object(Bucket="lake", Key="d/year=NOTINT/region=eu/f.parquet", Body=b"x")

    with pytest.raises(SchemaError):
        discover_partitions("lake", "d/", SCHEMA, client=client, strict=True)
