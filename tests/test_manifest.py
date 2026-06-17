"""Tests for lakeforge.manifest."""

from __future__ import annotations

import json
from datetime import date, datetime

import pytest

from lakeforge.manifest import Manifest, PartitionFiles, build_manifest
from lakeforge.partition import Partition
from lakeforge.schema import PartitionSchema

# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #


@pytest.fixture
def int_schema() -> PartitionSchema:
    return PartitionSchema.of(("year", "int"), ("month", "int"))


@pytest.fixture
def typed_schema() -> PartitionSchema:
    """A schema exercising every relevant column type."""
    return PartitionSchema.of(
        ("year", "int"),
        ("day", "date"),
        ("ts", "timestamp"),
        ("active", "boolean"),
        ("rate", "double"),
        "region",
    )


def _part(int_schema: PartitionSchema, year: int, month: int) -> Partition:
    return Partition({"year": year, "month": month}, int_schema)


# --------------------------------------------------------------------------- #
# PartitionFiles
# --------------------------------------------------------------------------- #


def test_partition_files_add_appends(int_schema: PartitionSchema) -> None:
    pf = PartitionFiles(_part(int_schema, 2024, 1))
    assert pf.files == []
    pf.add("a", "b")
    pf.add("c")
    assert pf.files == ["a", "b", "c"]


# --------------------------------------------------------------------------- #
# Manifest.add merging
# --------------------------------------------------------------------------- #


def test_add_creates_new_entry(int_schema: PartitionSchema) -> None:
    m = Manifest(int_schema)
    entry = m.add(_part(int_schema, 2024, 1), "f1", "f2")
    assert isinstance(entry, PartitionFiles)
    assert len(m.entries) == 1
    assert m.entries[0] is entry
    assert entry.files == ["f1", "f2"]


def test_add_merges_into_existing_partition(int_schema: PartitionSchema) -> None:
    m = Manifest(int_schema)
    first = m.add(_part(int_schema, 2024, 1), "f1")
    # A distinct partition value object but the same partition *path* must merge.
    merged = m.add(_part(int_schema, 2024, 1), "f2", "f3")
    assert merged is first
    assert len(m.entries) == 1
    assert merged.files == ["f1", "f2", "f3"]


def test_add_different_partitions_are_separate(int_schema: PartitionSchema) -> None:
    m = Manifest(int_schema)
    m.add(_part(int_schema, 2024, 1), "a")
    m.add(_part(int_schema, 2024, 2), "b")
    assert len(m.entries) == 2
    assert m.entries[0].files == ["a"]
    assert m.entries[1].files == ["b"]


def test_add_with_no_files_creates_empty_entry(int_schema: PartitionSchema) -> None:
    m = Manifest(int_schema)
    entry = m.add(_part(int_schema, 2024, 1))
    assert entry.files == []
    assert len(m.entries) == 1


# --------------------------------------------------------------------------- #
# total_files
# --------------------------------------------------------------------------- #


def test_total_files_empty(int_schema: PartitionSchema) -> None:
    assert Manifest(int_schema).total_files == 0


def test_total_files_counts_across_partitions(int_schema: PartitionSchema) -> None:
    m = Manifest(int_schema)
    m.add(_part(int_schema, 2024, 1), "a", "b")
    m.add(_part(int_schema, 2024, 2), "c")
    m.add(_part(int_schema, 2024, 1), "d")  # merges -> still total 4
    assert m.total_files == 4


# --------------------------------------------------------------------------- #
# all_files ordering
# --------------------------------------------------------------------------- #


def test_all_files_empty(int_schema: PartitionSchema) -> None:
    assert Manifest(int_schema).all_files() == []


def test_all_files_preserves_partition_then_insertion_order(
    int_schema: PartitionSchema,
) -> None:
    m = Manifest(int_schema)
    m.add(_part(int_schema, 2024, 1), "a1")
    m.add(_part(int_schema, 2024, 2), "b1")
    m.add(_part(int_schema, 2024, 1), "a2")  # appended to the first entry
    # Files appear in entry order (partition 1 first), then insertion order.
    assert m.all_files() == ["a1", "a2", "b1"]


# --------------------------------------------------------------------------- #
# to_dict / to_json / round-trip
# --------------------------------------------------------------------------- #


def test_to_dict_schema_section(int_schema: PartitionSchema) -> None:
    m = Manifest(int_schema)
    d = m.to_dict()
    assert d["schema"] == [
        {"name": "year", "type": "int"},
        {"name": "month", "type": "int"},
    ]
    assert d["partitions"] == []


def test_to_dict_partitions_section(int_schema: PartitionSchema) -> None:
    m = Manifest(int_schema)
    m.add(_part(int_schema, 2024, 1), "f1", "f2")
    d = m.to_dict()
    assert d["partitions"] == [
        {"values": {"year": 2024, "month": 1}, "files": ["f1", "f2"]}
    ]


def test_to_dict_files_is_a_copy(int_schema: PartitionSchema) -> None:
    m = Manifest(int_schema)
    entry = m.add(_part(int_schema, 2024, 1), "f1")
    d = m.to_dict()
    d["partitions"][0]["files"].append("mutated")
    assert entry.files == ["f1"]


def test_to_json_is_valid_and_indented(int_schema: PartitionSchema) -> None:
    m = Manifest(int_schema)
    m.add(_part(int_schema, 2024, 1), "f1")
    text = m.to_json()
    assert json.loads(text) == m.to_dict()
    assert "\n" in text  # default indent=2 produces a multi-line document


def test_to_json_indent_none_is_compact(int_schema: PartitionSchema) -> None:
    m = Manifest(int_schema)
    m.add(_part(int_schema, 2024, 1), "f1")
    text = m.to_json(indent=None)
    assert "\n" not in text
    assert json.loads(text) == m.to_dict()


def test_round_trip_preserves_typed_values(typed_schema: PartitionSchema) -> None:
    p = Partition(
        {
            "year": 2024,
            "day": date(2024, 1, 5),
            "ts": datetime(2024, 1, 5, 10, 30, 0),
            "active": True,
            "rate": 1.5,
            "region": "us-east-1",
        },
        typed_schema,
    )
    m = Manifest(typed_schema)
    m.add(p, "s3://bucket/f1.parquet", "s3://bucket/f2.parquet")

    restored = Manifest.from_json(m.to_json())

    assert len(restored.entries) == 1
    restored_part = restored.entries[0].partition
    # Typed values survive the JSON round-trip.
    assert restored_part.to_dict() == p.to_dict()
    # And the precise types are preserved, not just equal-looking strings.
    vals = restored_part.to_dict()
    assert isinstance(vals["year"], int)
    assert isinstance(vals["day"], date) and not isinstance(vals["day"], datetime)
    assert isinstance(vals["ts"], datetime)
    assert isinstance(vals["active"], bool)
    assert isinstance(vals["rate"], float)
    assert restored.entries[0].files == [
        "s3://bucket/f1.parquet",
        "s3://bucket/f2.parquet",
    ]


def test_round_trip_schema_columns(typed_schema: PartitionSchema) -> None:
    m = Manifest(typed_schema)
    restored = Manifest.from_dict(m.to_dict())
    assert restored.schema.names == typed_schema.names
    assert [c.type for c in restored.schema.columns] == [
        c.type for c in typed_schema.columns
    ]


def test_from_dict_merges_duplicate_partition_records(
    int_schema: PartitionSchema,
) -> None:
    # Two records with the same partition values collapse into one entry,
    # because from_dict goes through Manifest.add.
    data = {
        "schema": [{"name": "year", "type": "int"}, {"name": "month", "type": "int"}],
        "partitions": [
            {"values": {"year": 2024, "month": 1}, "files": ["a"]},
            {"values": {"year": 2024, "month": 1}, "files": ["b"]},
        ],
    }
    m = Manifest.from_dict(data)
    assert len(m.entries) == 1
    assert m.entries[0].files == ["a", "b"]


# --------------------------------------------------------------------------- #
# date / timestamp serialize to strings
# --------------------------------------------------------------------------- #


def test_date_and_timestamp_serialize_to_strings(
    typed_schema: PartitionSchema,
) -> None:
    p = Partition(
        {
            "year": 2024,
            "day": date(2024, 1, 5),
            "ts": datetime(2024, 1, 5, 10, 30, 0),
            "active": True,
            "rate": 2.0,
            "region": "eu",
        },
        typed_schema,
    )
    m = Manifest(typed_schema)
    m.add(p, "f")
    values = m.to_dict()["partitions"][0]["values"]

    assert values["day"] == "2024-01-05"
    assert isinstance(values["day"], str)
    assert values["ts"] == str(datetime(2024, 1, 5, 10, 30, 0))
    assert isinstance(values["ts"], str)
    # Scalars that are natively JSON-friendly are NOT stringified.
    assert values["year"] == 2024 and isinstance(values["year"], int)
    assert values["active"] is True
    assert values["rate"] == 2.0 and isinstance(values["rate"], float)


def test_to_dict_is_json_serializable_with_temporal_values(
    typed_schema: PartitionSchema,
) -> None:
    p = Partition(
        {
            "year": 2024,
            "day": date(2024, 3, 1),
            "ts": datetime(2024, 3, 1, 0, 0, 0),
            "active": False,
            "rate": 0.0,
            "region": "ap",
        },
        typed_schema,
    )
    m = Manifest(typed_schema)
    m.add(p, "f")
    # Would raise TypeError if a raw date/datetime leaked through.
    json.dumps(m.to_dict())


# --------------------------------------------------------------------------- #
# to_redshift_manifest
# --------------------------------------------------------------------------- #


def test_to_redshift_manifest_entries_and_defaults(int_schema: PartitionSchema) -> None:
    m = Manifest(int_schema)
    m.add(_part(int_schema, 2024, 1), "s3://b/f1", "s3://b/f2")
    m.add(_part(int_schema, 2024, 2), "s3://b/f3")

    payload = json.loads(m.to_redshift_manifest())
    assert payload == {
        "entries": [
            {"url": "s3://b/f1", "mandatory": True},
            {"url": "s3://b/f2", "mandatory": True},
            {"url": "s3://b/f3", "mandatory": True},
        ]
    }


def test_to_redshift_manifest_mandatory_false(int_schema: PartitionSchema) -> None:
    m = Manifest(int_schema)
    m.add(_part(int_schema, 2024, 1), "s3://b/f1")
    payload = json.loads(m.to_redshift_manifest(mandatory=False))
    assert payload["entries"] == [{"url": "s3://b/f1", "mandatory": False}]


def test_to_redshift_manifest_order_matches_all_files(
    int_schema: PartitionSchema,
) -> None:
    m = Manifest(int_schema)
    m.add(_part(int_schema, 2024, 1), "a1")
    m.add(_part(int_schema, 2024, 2), "b1")
    m.add(_part(int_schema, 2024, 1), "a2")
    payload = json.loads(m.to_redshift_manifest())
    assert [e["url"] for e in payload["entries"]] == m.all_files()


def test_to_redshift_manifest_empty(int_schema: PartitionSchema) -> None:
    payload = json.loads(Manifest(int_schema).to_redshift_manifest())
    assert payload == {"entries": []}


# --------------------------------------------------------------------------- #
# build_manifest
# --------------------------------------------------------------------------- #


def test_build_manifest_basic(int_schema: PartitionSchema) -> None:
    pa = _part(int_schema, 2024, 1)
    pb = _part(int_schema, 2024, 2)
    m = build_manifest(int_schema, [(pa, ["x1", "x2"]), (pb, ["y1"])])
    assert isinstance(m, Manifest)
    assert m.schema is int_schema
    assert m.total_files == 3
    assert m.all_files() == ["x1", "x2", "y1"]


def test_build_manifest_merges_repeated_partitions(int_schema: PartitionSchema) -> None:
    pa = _part(int_schema, 2024, 1)
    pb = _part(int_schema, 2024, 2)
    m = build_manifest(
        int_schema, [(pa, ["x1", "x2"]), (pb, ["y1"]), (pa, ["x3"])]
    )
    assert len(m.entries) == 2
    assert m.all_files() == ["x1", "x2", "x3", "y1"]


def test_build_manifest_accepts_arbitrary_iterables(int_schema: PartitionSchema) -> None:
    pa = _part(int_schema, 2024, 1)

    def gen():
        yield (pa, (f"f{i}" for i in range(3)))

    m = build_manifest(int_schema, gen())
    assert m.all_files() == ["f0", "f1", "f2"]


def test_build_manifest_empty(int_schema: PartitionSchema) -> None:
    m = build_manifest(int_schema, [])
    assert m.entries == []
    assert m.total_files == 0
