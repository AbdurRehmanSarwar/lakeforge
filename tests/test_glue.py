"""Tests for lakeforge.glue DDL generation.

These tests encode the *current* behavior of the pure string builders in
``lakeforge.glue``. Where the implementation has a quirk (e.g. timestamp
partition literals use ISO ``T`` separators while the projection format
property uses a space), the test asserts the actual behavior and the quirk is
noted in the test docstring.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from lakeforge import glue
from lakeforge.partition import Partition
from lakeforge.schema import PartitionSchema


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _schema(*specs):
    return PartitionSchema.of(*specs)


# --------------------------------------------------------------------------- #
# add_partition_ddl: literal quoting
# --------------------------------------------------------------------------- #
def test_add_partition_string_value_is_quoted():
    sch = _schema(("region", "string"))
    p = Partition({"region": "us"}, sch)
    ddl = glue.add_partition_ddl("events", p, "s3://bucket/events")
    assert "PARTITION (region='us')" in ddl


def test_add_partition_int_value_is_unquoted():
    sch = _schema(("year", "int"))
    p = Partition({"year": 2024}, sch)
    ddl = glue.add_partition_ddl("events", p, "s3://bucket/events")
    assert "PARTITION (year=2024)" in ddl
    assert "year='2024'" not in ddl


def test_add_partition_double_value_is_unquoted():
    sch = _schema(("ratio", "double"))
    p = Partition({"ratio": 1.5}, sch)
    ddl = glue.add_partition_ddl("events", p, "s3://bucket/events")
    assert "PARTITION (ratio=1.5)" in ddl
    assert "ratio='1.5'" not in ddl


def test_add_partition_boolean_value_is_quoted():
    """Booleans live in the quoted-types set, so they render as 'true'/'false'."""
    sch = _schema(("active", "boolean"))
    p = Partition({"active": True}, sch)
    ddl = glue.add_partition_ddl("events", p, "s3://bucket/events")
    assert "PARTITION (active='true')" in ddl


def test_add_partition_boolean_false_value_is_quoted():
    sch = _schema(("active", "boolean"))
    p = Partition({"active": False}, sch)
    ddl = glue.add_partition_ddl("events", p, "s3://bucket/events")
    assert "PARTITION (active='false')" in ddl


def test_add_partition_date_value_is_quoted():
    sch = _schema(("d", "date"))
    p = Partition({"d": date(2024, 1, 5)}, sch)
    ddl = glue.add_partition_ddl("events", p, "s3://bucket/events")
    assert "PARTITION (d='2024-01-05')" in ddl


def test_add_partition_timestamp_value_is_quoted_with_iso_t_separator():
    """The PARTITION literal uses ``datetime.isoformat`` -> a 'T' separator."""
    sch = _schema(("ts", "timestamp"))
    p = Partition({"ts": datetime(2024, 1, 5, 13, 30, 0)}, sch)
    ddl = glue.add_partition_ddl("events", p, "s3://bucket/events")
    assert "PARTITION (ts='2024-01-05T13:30:00')" in ddl


def test_add_partition_mixed_types_full_statement():
    sch = _schema(
        ("region", "string"),
        ("year", "int"),
        ("ratio", "double"),
        ("active", "boolean"),
    )
    p = Partition(
        {"region": "us-east", "year": 2024, "ratio": 0.25, "active": True}, sch
    )
    ddl = glue.add_partition_ddl("events", p, "s3://bucket/events")
    assert ddl == (
        "ALTER TABLE events ADD IF NOT EXISTS PARTITION "
        "(region='us-east', year=2024, ratio=0.25, active='true') "
        "LOCATION 's3://bucket/events/region=us-east/year=2024/ratio=0.25/active=true/';"
    )


# --------------------------------------------------------------------------- #
# add_partition_ddl: single-quote escaping
# --------------------------------------------------------------------------- #
def test_add_partition_single_quote_in_string_is_doubled():
    """A single quote in a string value is SQL-escaped by doubling it."""
    sch = _schema(("name", "string"))
    p = Partition({"name": "O'Brien"}, sch)
    ddl = glue.add_partition_ddl("t", p, "s3://b/x")
    assert "PARTITION (name='O''Brien')" in ddl


def test_add_partition_multiple_single_quotes_each_doubled():
    sch = _schema(("name", "string"))
    p = Partition({"name": "a'b'c"}, sch)
    ddl = glue.add_partition_ddl("t", p, "s3://b/x")
    assert "name='a''b''c'" in ddl


def test_add_partition_single_quote_is_percent_encoded_in_location():
    """The LOCATION uses the percent-encoded path, not the SQL-escaped literal."""
    sch = _schema(("name", "string"))
    p = Partition({"name": "O'Brien"}, sch)
    ddl = glue.add_partition_ddl("t", p, "s3://b/x")
    assert "LOCATION 's3://b/x/name=O%27Brien/';" in ddl


# --------------------------------------------------------------------------- #
# add_partition_ddl: database qualifier & if_not_exists toggle
# --------------------------------------------------------------------------- #
def test_add_partition_database_qualifier():
    sch = _schema(("year", "int"))
    p = Partition({"year": 2024}, sch)
    ddl = glue.add_partition_ddl("events", p, "s3://b/e", database="analytics")
    assert ddl.startswith("ALTER TABLE analytics.events ADD ")


def test_add_partition_no_database_is_unqualified():
    sch = _schema(("year", "int"))
    p = Partition({"year": 2024}, sch)
    ddl = glue.add_partition_ddl("events", p, "s3://b/e")
    assert ddl.startswith("ALTER TABLE events ADD ")
    assert "." not in ddl.split(" ADD ")[0]


def test_add_partition_if_not_exists_true_default():
    sch = _schema(("year", "int"))
    p = Partition({"year": 2024}, sch)
    ddl = glue.add_partition_ddl("events", p, "s3://b/e")
    assert "ADD IF NOT EXISTS PARTITION" in ddl


def test_add_partition_if_not_exists_false_omits_guard():
    sch = _schema(("year", "int"))
    p = Partition({"year": 2024}, sch)
    ddl = glue.add_partition_ddl("events", p, "s3://b/e", if_not_exists=False)
    assert "IF NOT EXISTS" not in ddl
    assert "ADD PARTITION" in ddl


def test_add_partition_location_has_trailing_slash():
    sch = _schema(("year", "int"))
    p = Partition({"year": 2024}, sch)
    ddl = glue.add_partition_ddl("events", p, "s3://bucket/events/")
    # base trailing slash is normalized away; path adds exactly one.
    assert "LOCATION 's3://bucket/events/year=2024/';" in ddl


def test_add_partition_statement_ends_with_semicolon():
    sch = _schema(("year", "int"))
    p = Partition({"year": 2024}, sch)
    ddl = glue.add_partition_ddl("events", p, "s3://b/e")
    assert ddl.endswith(";")


# --------------------------------------------------------------------------- #
# add_partitions_ddl
# --------------------------------------------------------------------------- #
def test_add_partitions_multiple_clauses():
    sch = _schema(("name", "string"), ("year", "int"))
    p1 = Partition({"name": "alpha", "year": 2023}, sch)
    p2 = Partition({"name": "beta", "year": 2024}, sch)
    ddl = glue.add_partitions_ddl("t", [p1, p2], "s3://b/x")
    expected = (
        "ALTER TABLE t ADD IF NOT EXISTS\n"
        "  PARTITION (name='alpha', year=2023) "
        "LOCATION 's3://b/x/name=alpha/year=2023/'\n"
        "  PARTITION (name='beta', year=2024) "
        "LOCATION 's3://b/x/name=beta/year=2024/';"
    )
    assert ddl == expected


def test_add_partitions_single_clause_no_if_not_exists():
    sch = _schema(("year", "int"))
    p = Partition({"year": 2024}, sch)
    ddl = glue.add_partitions_ddl("t", [p], "s3://b/x", if_not_exists=False)
    assert "IF NOT EXISTS" not in ddl
    # When the guard is off, current behavior leaves a trailing space after ADD.
    assert ddl.startswith("ALTER TABLE t ADD \n  PARTITION (year=2024)")


def test_add_partitions_database_qualifier():
    sch = _schema(("year", "int"))
    p = Partition({"year": 2024}, sch)
    ddl = glue.add_partitions_ddl("t", [p], "s3://b/x", database="db")
    assert ddl.startswith("ALTER TABLE db.t ADD")


def test_add_partitions_accepts_generator():
    sch = _schema(("year", "int"))
    parts = (Partition({"year": y}, sch) for y in (2021, 2022))
    ddl = glue.add_partitions_ddl("t", parts, "s3://b/x")
    assert "year=2021" in ddl and "year=2022" in ddl


def test_add_partitions_empty_raises_value_error():
    with pytest.raises(ValueError, match="at least one partition"):
        glue.add_partitions_ddl("t", [], "s3://b/x")


def test_add_partitions_empty_generator_raises_value_error():
    with pytest.raises(ValueError):
        glue.add_partitions_ddl("t", (p for p in []), "s3://b/x")


def test_add_partitions_ends_with_semicolon():
    sch = _schema(("year", "int"))
    p = Partition({"year": 2024}, sch)
    ddl = glue.add_partitions_ddl("t", [p], "s3://b/x")
    assert ddl.endswith(";")


# --------------------------------------------------------------------------- #
# create_table_ddl
# --------------------------------------------------------------------------- #
def test_create_table_basic_full_statement():
    sch = _schema(("year", "int"), ("region", "string"))
    ddl = glue.create_table_ddl(
        "events",
        {"id": "bigint", "payload": "string"},
        sch,
        "s3://bucket/events",
        database="db",
    )
    expected = (
        "CREATE EXTERNAL TABLE IF NOT EXISTS db.events (\n"
        "  id bigint,\n"
        "  payload string\n"
        ") PARTITIONED BY (year bigint, region string)\n"
        "STORED AS PARQUET\n"
        "LOCATION 's3://bucket/events/';"
    )
    assert ddl == expected


def test_create_table_partition_uses_athena_types():
    """Partition int -> bigint, boolean -> boolean in PARTITIONED BY."""
    sch = _schema(("year", "int"), ("flag", "boolean"))
    ddl = glue.create_table_ddl("t", {"id": "bigint"}, sch, "s3://b/t")
    assert "PARTITIONED BY (year bigint, flag boolean)" in ddl


def test_create_table_location_is_normalized_to_single_trailing_slash():
    sch = _schema(("year", "int"))
    ddl = glue.create_table_ddl("t", {"id": "bigint"}, sch, "s3://bucket/t///")
    assert "LOCATION 's3://bucket/t/';" in ddl


def test_create_table_location_without_slash_gets_one():
    sch = _schema(("year", "int"))
    ddl = glue.create_table_ddl("t", {"id": "bigint"}, sch, "s3://bucket/t")
    assert "LOCATION 's3://bucket/t/';" in ddl


def test_create_table_if_not_exists_false_omits_guard():
    sch = _schema(("year", "int"))
    ddl = glue.create_table_ddl(
        "t", {"id": "bigint"}, sch, "s3://b/t", if_not_exists=False
    )
    assert ddl.startswith("CREATE EXTERNAL TABLE t (")
    assert "IF NOT EXISTS" not in ddl


def test_create_table_custom_stored_as():
    sch = _schema(("year", "int"))
    ddl = glue.create_table_ddl(
        "t", {"id": "bigint"}, sch, "s3://b/t", stored_as="ORC"
    )
    assert "STORED AS ORC" in ddl


def test_create_table_no_database_unqualified():
    sch = _schema(("year", "int"))
    ddl = glue.create_table_ddl("t", {"id": "bigint"}, sch, "s3://b/t")
    assert ddl.startswith("CREATE EXTERNAL TABLE IF NOT EXISTS t (")


def test_create_table_with_table_properties():
    sch = _schema(("year", "int"))
    ddl = glue.create_table_ddl(
        "t",
        {"id": "bigint"},
        sch,
        "s3://b/t",
        table_properties={"classification": "parquet", "compression": "snappy"},
    )
    assert (
        "TBLPROPERTIES ('classification'='parquet', 'compression'='snappy')" in ddl
    )
    assert ddl.endswith(");")


def test_create_table_without_table_properties_has_no_tblproperties():
    sch = _schema(("year", "int"))
    ddl = glue.create_table_ddl("t", {"id": "bigint"}, sch, "s3://b/t")
    assert "TBLPROPERTIES" not in ddl


def test_create_table_empty_table_properties_omitted():
    """Falsy (empty) table_properties means no TBLPROPERTIES clause."""
    sch = _schema(("year", "int"))
    ddl = glue.create_table_ddl(
        "t", {"id": "bigint"}, sch, "s3://b/t", table_properties={}
    )
    assert "TBLPROPERTIES" not in ddl


def test_create_table_column_partition_overlap_raises_value_error():
    sch = _schema(("year", "int"), ("region", "string"))
    with pytest.raises(ValueError, match="appear in both"):
        glue.create_table_ddl(
            "events",
            {"year": "bigint", "id": "bigint"},
            sch,
            "s3://b/events",
        )


def test_create_table_overlap_error_lists_offending_columns():
    sch = _schema(("year", "int"), ("region", "string"))
    with pytest.raises(ValueError) as excinfo:
        glue.create_table_ddl(
            "events",
            {"year": "bigint", "region": "string", "id": "bigint"},
            sch,
            "s3://b/events",
        )
    msg = str(excinfo.value)
    assert "year" in msg and "region" in msg


def test_create_table_ends_with_semicolon():
    sch = _schema(("year", "int"))
    ddl = glue.create_table_ddl("t", {"id": "bigint"}, sch, "s3://b/t")
    assert ddl.endswith(";")


# --------------------------------------------------------------------------- #
# msck_repair
# --------------------------------------------------------------------------- #
def test_msck_repair_unqualified():
    assert glue.msck_repair("events") == "MSCK REPAIR TABLE events;"


def test_msck_repair_with_database():
    assert glue.msck_repair("events", database="db") == "MSCK REPAIR TABLE db.events;"


# --------------------------------------------------------------------------- #
# projection_properties: integer
# --------------------------------------------------------------------------- #
def test_projection_integer_range_interval_digits():
    sch = _schema(("year", "int"), ("month", "int"))
    props = glue.projection_properties(
        sch,
        "s3://b/${year}/${month}",
        ranges={"year": (2020, 2025), "month": (1, 12)},
        interval={"month": 1},
        digits={"month": 2},
    )
    assert props["projection.enabled"] == "true"
    assert props["storage.location.template"] == "s3://b/${year}/${month}"
    assert props["projection.year.type"] == "integer"
    assert props["projection.year.range"] == "2020,2025"
    # year has neither interval nor digits configured.
    assert "projection.year.interval" not in props
    assert "projection.year.digits" not in props
    assert props["projection.month.type"] == "integer"
    assert props["projection.month.range"] == "1,12"
    assert props["projection.month.interval"] == "1"
    assert props["projection.month.digits"] == "2"


def test_projection_integer_minimal_range_only():
    sch = _schema(("year", "int"))
    props = glue.projection_properties(
        sch, "s3://b/${year}", ranges={"year": (2020, 2025)}
    )
    assert props["projection.year.type"] == "integer"
    assert props["projection.year.range"] == "2020,2025"
    assert "projection.year.interval" not in props
    assert "projection.year.digits" not in props


def test_projection_integer_missing_range_raises_value_error():
    sch = _schema(("year", "int"))
    with pytest.raises(ValueError, match="requires a range"):
        glue.projection_properties(sch, "s3://b/${year}")


# --------------------------------------------------------------------------- #
# projection_properties: date / timestamp
# --------------------------------------------------------------------------- #
def test_projection_date_format():
    sch = _schema(("d", "date"))
    props = glue.projection_properties(
        sch, "s3://b/${d}", ranges={"d": ("2024-01-01", "NOW")}
    )
    assert props["projection.d.type"] == "date"
    assert props["projection.d.range"] == "2024-01-01,NOW"
    assert props["projection.d.format"] == "yyyy-MM-dd"


def test_projection_timestamp_format():
    sch = _schema(("ts", "timestamp"))
    props = glue.projection_properties(
        sch, "s3://b/${ts}", ranges={"ts": ("2024-01-01 00:00:00", "NOW")}
    )
    assert props["projection.ts.type"] == "date"
    assert props["projection.ts.range"] == "2024-01-01 00:00:00,NOW"
    # The format matches the 'T'-separated ISO output of Partition.path() so
    # Athena computes the same S3 prefixes the library renders.
    assert props["projection.ts.format"] == "yyyy-MM-dd'T'HH:mm:ss"


def test_projection_date_missing_range_raises_value_error():
    sch = _schema(("d", "date"))
    with pytest.raises(ValueError, match="requires a range"):
        glue.projection_properties(sch, "s3://b/${d}")


def test_projection_timestamp_missing_range_raises_value_error():
    sch = _schema(("ts", "timestamp"))
    with pytest.raises(ValueError, match="requires a range"):
        glue.projection_properties(sch, "s3://b/${ts}")


# --------------------------------------------------------------------------- #
# projection_properties: enum (string)
# --------------------------------------------------------------------------- #
def test_projection_enum_strings():
    sch = _schema(("region", "string"))
    props = glue.projection_properties(
        sch, "s3://b/${region}", enum_values={"region": ["us", "eu", "ap"]}
    )
    assert props["projection.region.type"] == "enum"
    assert props["projection.region.values"] == "us,eu,ap"


def test_projection_enum_single_value():
    sch = _schema(("region", "string"))
    props = glue.projection_properties(
        sch, "s3://b/${region}", enum_values={"region": ["us"]}
    )
    assert props["projection.region.values"] == "us"


def test_projection_enum_missing_values_raises_value_error():
    sch = _schema(("region", "string"))
    with pytest.raises(ValueError, match="requires enum_values"):
        glue.projection_properties(sch, "s3://b/${region}")


def test_projection_enum_empty_values_raises_value_error():
    """An empty enum list is falsy and treated the same as missing."""
    sch = _schema(("region", "string"))
    with pytest.raises(ValueError, match="requires enum_values"):
        glue.projection_properties(
            sch, "s3://b/${region}", enum_values={"region": []}
        )


# --------------------------------------------------------------------------- #
# projection_properties: combined / boolean & double fall through to enum branch
# --------------------------------------------------------------------------- #
def test_projection_mixed_schema():
    sch = _schema(("year", "int"), ("d", "date"), ("region", "string"))
    props = glue.projection_properties(
        sch,
        "s3://b/${year}/${d}/${region}",
        ranges={"year": (2020, 2024), "d": ("2024-01-01", "NOW")},
        enum_values={"region": ["us", "eu"]},
    )
    assert props["projection.year.type"] == "integer"
    assert props["projection.d.type"] == "date"
    assert props["projection.region.type"] == "enum"


def test_projection_double_column_requires_enum_values():
    """Non-int/date/timestamp columns (e.g. double) hit the enum branch."""
    sch = _schema(("ratio", "double"))
    with pytest.raises(ValueError, match="requires enum_values"):
        glue.projection_properties(sch, "s3://b/${ratio}")


def test_projection_result_is_plain_dict():
    sch = _schema(("region", "string"))
    props = glue.projection_properties(
        sch, "s3://b/${region}", enum_values={"region": ["us"]}
    )
    assert isinstance(props, dict)
