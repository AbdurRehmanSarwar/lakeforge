"""Tests for lakeforge.partition.

Covers Partition construction/coercion, path rendering with percent-encoding,
S3 URI joining, parsing from bare paths / full S3 keys, error handling, and
build_partitions.
"""

from __future__ import annotations

import datetime

import pytest

from lakeforge.errors import PartitionParseError, SchemaError
from lakeforge.partition import Partition, build_partitions
from lakeforge.schema import (
    PartitionSchema,
)

# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #


@pytest.fixture
def ymd_schema() -> PartitionSchema:
    """year=int / month=int / day=int."""
    return PartitionSchema.of(("year", "int"), ("month", "int"), ("day", "int"))


@pytest.fixture
def region_schema() -> PartitionSchema:
    """year=int / region=string."""
    return PartitionSchema.of(("year", "int"), "region")


@pytest.fixture
def str_schema() -> PartitionSchema:
    """Single string column."""
    return PartitionSchema.of("key")


# --------------------------------------------------------------------------- #
# Construction + coercion
# --------------------------------------------------------------------------- #


def test_construct_with_string_values_coerces_to_typed(ymd_schema):
    p = Partition({"year": "2024", "month": "1", "day": "5"}, ymd_schema)
    assert p.values == {"year": 2024, "month": 1, "day": 5}
    assert all(isinstance(v, int) for v in p.values.values())


def test_construct_with_native_values_passes_through(ymd_schema):
    # Non-str values are not re-parsed; they pass through untouched.
    p = Partition({"year": 2024, "month": 1, "day": 5}, ymd_schema)
    assert p.values == {"year": 2024, "month": 1, "day": 5}


def test_values_are_reordered_into_schema_order(ymd_schema):
    p = Partition({"day": 5, "year": 2024, "month": 1}, ymd_schema)
    assert list(p.values.keys()) == ["year", "month", "day"]


def test_of_classmethod_builds_partition(ymd_schema):
    p = Partition.of(ymd_schema, year=2024, month=1, day=5)
    assert p.values == {"year": 2024, "month": 1, "day": 5}


def test_of_classmethod_coerces_string_kwargs(ymd_schema):
    p = Partition.of(ymd_schema, year="2024", month="1", day="5")
    assert p.values == {"year": 2024, "month": 1, "day": 5}


def test_missing_value_raises_schema_error(ymd_schema):
    with pytest.raises(SchemaError):
        Partition({"year": 2024, "month": 1}, ymd_schema)


def test_extra_value_raises_schema_error(ymd_schema):
    with pytest.raises(SchemaError):
        Partition({"year": 2024, "month": 1, "day": 5, "hour": 3}, ymd_schema)


def test_bad_string_value_raises_schema_error(ymd_schema):
    with pytest.raises(SchemaError):
        Partition({"year": "notanint", "month": 1, "day": 5}, ymd_schema)


def test_partition_is_frozen(ymd_schema):
    p = Partition.of(ymd_schema, year=2024, month=1, day=5)
    with pytest.raises(AttributeError):  # FrozenInstanceError subclasses AttributeError
        p.values = {}  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# Mapping protocol
# --------------------------------------------------------------------------- #


def test_getitem(ymd_schema):
    p = Partition.of(ymd_schema, year=2024, month=1, day=5)
    assert p["year"] == 2024
    assert p["day"] == 5


def test_iter_yields_keys_in_schema_order(ymd_schema):
    p = Partition.of(ymd_schema, year=2024, month=1, day=5)
    assert list(iter(p)) == ["year", "month", "day"]


def test_len(ymd_schema):
    p = Partition.of(ymd_schema, year=2024, month=1, day=5)
    assert len(p) == 3


def test_to_dict_returns_plain_dict_copy(ymd_schema):
    p = Partition.of(ymd_schema, year=2024, month=1, day=5)
    d = p.to_dict()
    assert d == {"year": 2024, "month": 1, "day": 5}
    d["year"] = 0  # mutating the copy must not affect the partition
    assert p["year"] == 2024


# --------------------------------------------------------------------------- #
# path()
# --------------------------------------------------------------------------- #


def test_path_basic(ymd_schema):
    p = Partition.of(ymd_schema, year=2024, month=1, day=5)
    assert p.path() == "year=2024/month=1/day=5"


def test_path_int_not_zero_padded(ymd_schema):
    # Integer columns render without zero-padding (month=1, not month=01).
    p = Partition.of(ymd_schema, year=2024, month=1, day=5)
    assert "month=1/" in p.path() + "/"
    assert "month=01" not in p.path()


def test_path_zero_padded_via_string_column():
    s = PartitionSchema.of("year", "month")
    p = Partition.of(s, year="2024", month="01")
    assert p.path() == "year=2024/month=01"


def test_path_trailing_slash(ymd_schema):
    p = Partition.of(ymd_schema, year=2024, month=1, day=5)
    assert p.path(trailing_slash=True) == "year=2024/month=1/day=5/"


def test_path_encodes_spaces(region_schema):
    p = Partition.of(region_schema, year=2024, region="us east")
    assert p.path() == "year=2024/region=us%20east"


def test_path_encodes_slash(region_schema):
    p = Partition.of(region_schema, year=2024, region="a/b")
    assert p.path() == "year=2024/region=a%2Fb"


def test_path_encodes_equals(region_schema):
    p = Partition.of(region_schema, year=2024, region="x=y")
    assert p.path() == "year=2024/region=x%3Dy"


def test_path_leaves_safe_chars_unencoded(region_schema):
    p = Partition.of(region_schema, year=2024, region="a-b_c.d:e")
    assert p.path() == "year=2024/region=a-b_c.d:e"


def test_path_encode_false_leaves_raw(region_schema):
    p = Partition.of(region_schema, year=2024, region="us east")
    assert p.path(encode=False) == "year=2024/region=us east"


# --------------------------------------------------------------------------- #
# path() <-> parse round-trips
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "value",
    ["us east", "a/b", "x=y", "weird %20 already", "a-b_c.d:e", "plain"],
)
def test_path_roundtrip_through_parse(region_schema, value):
    p = Partition.of(region_schema, year=2024, region=value)
    rendered = p.path()
    reparsed = Partition.parse(rendered, region_schema)
    assert reparsed["region"] == value
    assert reparsed["year"] == 2024
    assert reparsed == p


def test_roundtrip_with_trailing_slash(region_schema):
    p = Partition.of(region_schema, year=2024, region="a/b")
    reparsed = Partition.parse(p.path(trailing_slash=True), region_schema)
    assert reparsed == p


# --------------------------------------------------------------------------- #
# s3_uri()
# --------------------------------------------------------------------------- #


def test_s3_uri_base_without_trailing_slash(ymd_schema):
    p = Partition.of(ymd_schema, year=2024, month=1, day=5)
    uri = p.s3_uri("s3://bucket/prefix")
    assert uri == "s3://bucket/prefix/year=2024/month=1/day=5/"


def test_s3_uri_base_with_trailing_slash(ymd_schema):
    p = Partition.of(ymd_schema, year=2024, month=1, day=5)
    uri = p.s3_uri("s3://bucket/prefix/")
    assert uri == "s3://bucket/prefix/year=2024/month=1/day=5/"


def test_s3_uri_base_with_multiple_trailing_slashes(ymd_schema):
    p = Partition.of(ymd_schema, year=2024, month=1, day=5)
    uri = p.s3_uri("s3://bucket/prefix///")
    assert uri == "s3://bucket/prefix/year=2024/month=1/day=5/"


def test_s3_uri_scheme_preserved(ymd_schema):
    p = Partition.of(ymd_schema, year=2024, month=1, day=5)
    assert p.s3_uri("s3://bucket").startswith("s3://bucket/")


def test_s3_uri_no_trailing_slash(ymd_schema):
    p = Partition.of(ymd_schema, year=2024, month=1, day=5)
    uri = p.s3_uri("s3://bucket/prefix", trailing_slash=False)
    assert uri == "s3://bucket/prefix/year=2024/month=1/day=5"


def test_s3_uri_plain_prefix_base(ymd_schema):
    p = Partition.of(ymd_schema, year=2024, month=1, day=5)
    uri = p.s3_uri("data/lake")
    assert uri == "data/lake/year=2024/month=1/day=5/"


# --------------------------------------------------------------------------- #
# parse()
# --------------------------------------------------------------------------- #


def test_parse_bare_path(ymd_schema):
    p = Partition.parse("year=2024/month=1/day=5", ymd_schema)
    assert p.values == {"year": 2024, "month": 1, "day": 5}


def test_parse_path_with_leading_and_trailing_slashes(ymd_schema):
    p = Partition.parse("/year=2024/month=1/day=5/", ymd_schema)
    assert p.values == {"year": 2024, "month": 1, "day": 5}


def test_parse_full_s3_key_with_prefix_and_filename(ymd_schema):
    key = "s3://bucket/prefix/year=2024/month=1/day=5/part-0000.parquet"
    p = Partition.parse(key, ymd_schema)
    assert p.values == {"year": 2024, "month": 1, "day": 5}


def test_parse_ignores_leading_prefix_segments(ymd_schema):
    key = "some/random/prefix/year=2024/month=1/day=5"
    p = Partition.parse(key, ymd_schema)
    assert p.values == {"year": 2024, "month": 1, "day": 5}


def test_parse_ignores_unrelated_equals_segments(ymd_schema):
    # A leading segment with '=' that is not a schema column must be ignored.
    key = "foo=bar/year=2024/month=1/day=5"
    p = Partition.parse(key, ymd_schema)
    assert p.values == {"year": 2024, "month": 1, "day": 5}


def test_parse_takes_first_occurrence_of_a_column(ymd_schema):
    # Duplicate keys: the first wins (key not in found).
    key = "year=2024/month=1/day=5/year=1999"
    p = Partition.parse(key, ymd_schema)
    assert p["year"] == 2024


def test_parse_decodes_percent_encoding(region_schema):
    p = Partition.parse("year=2024/region=us%20east", region_schema)
    assert p["region"] == "us east"


def test_parse_decodes_encoded_slash(region_schema):
    p = Partition.parse("year=2024/region=a%2Fb", region_schema)
    assert p["region"] == "a/b"


def test_parse_missing_column_raises(ymd_schema):
    with pytest.raises(PartitionParseError) as exc:
        Partition.parse("year=2024/month=1", ymd_schema)
    assert "day" in str(exc.value)


def test_parse_no_partition_segments_raises(ymd_schema):
    with pytest.raises(PartitionParseError):
        Partition.parse("just/a/plain/path", ymd_schema)


def test_parse_accepts_schema_string_spec():
    p = Partition.parse("year=2024/month=1", "year:int,month:int")
    assert p.values == {"year": 2024, "month": 1}


def test_parse_accepts_iterable_schema_spec():
    p = Partition.parse(
        "year=2024/region=us", [("year", "int"), "region"]
    )
    assert p.values == {"year": 2024, "region": "us"}


def test_parse_date_column():
    s = PartitionSchema.of(("dt", "date"))
    p = Partition.parse("dt=2024-01-05", s)
    assert p["dt"] == datetime.date(2024, 1, 5)


def test_parse_strips_whitespace_in_key():
    # parse() strips the key before comparing against schema names.
    s = PartitionSchema.of(("year", "int"))
    p = Partition.parse(" year =2024", s)
    assert p["year"] == 2024


# --------------------------------------------------------------------------- #
# build_partitions
# --------------------------------------------------------------------------- #


def test_build_partitions_from_dicts(ymd_schema):
    rows = [
        {"year": 2024, "month": 1, "day": 5},
        {"year": "2024", "month": "2", "day": "6"},
    ]
    parts = build_partitions(ymd_schema, rows)
    assert len(parts) == 2
    assert all(isinstance(p, Partition) for p in parts)
    assert parts[0].values == {"year": 2024, "month": 1, "day": 5}
    assert parts[1].values == {"year": 2024, "month": 2, "day": 6}


def test_build_partitions_empty(ymd_schema):
    assert build_partitions(ymd_schema, []) == []


def test_build_partitions_from_generator(ymd_schema):
    rows = ({"year": y, "month": 1, "day": 1} for y in (2023, 2024))
    parts = build_partitions(ymd_schema, rows)
    assert [p["year"] for p in parts] == [2023, 2024]


def test_build_partitions_propagates_validation_error(ymd_schema):
    with pytest.raises(SchemaError):
        build_partitions(ymd_schema, [{"year": 2024, "month": 1}])


# --------------------------------------------------------------------------- #
# Equality / hashing of frozen dataclass
# --------------------------------------------------------------------------- #


def test_equal_partitions_compare_equal(ymd_schema):
    a = Partition.of(ymd_schema, year=2024, month=1, day=5)
    b = Partition.of(ymd_schema, year=2024, month=1, day=5)
    assert a == b


def test_different_partitions_not_equal(ymd_schema):
    a = Partition.of(ymd_schema, year=2024, month=1, day=5)
    b = Partition.of(ymd_schema, year=2024, month=1, day=6)
    assert a != b
