"""Tests for :func:`lakeforge.glue.drop_partition_ddl`."""

from __future__ import annotations

import pytest

from lakeforge import Partition, schema
from lakeforge.errors import LakeForgeError
from lakeforge.glue import drop_partition_ddl


def test_drop_partition_basic_quoting():
    sch = schema(("year", "int"), "region")
    p = Partition.of(sch, year=2024, region="us")
    ddl = drop_partition_ddl("events", p)
    assert ddl == "ALTER TABLE events DROP IF EXISTS PARTITION (year=2024, region='us');"


def test_drop_partition_with_database():
    sch = schema(("year", "int"))
    p = Partition.of(sch, year=2024)
    ddl = drop_partition_ddl("events", p, database="analytics")
    assert ddl.startswith("ALTER TABLE analytics.events DROP IF EXISTS PARTITION (year=2024)")


def test_drop_partition_without_if_exists():
    sch = schema(("year", "int"))
    p = Partition.of(sch, year=2024)
    ddl = drop_partition_ddl("events", p, if_exists=False)
    assert ddl == "ALTER TABLE events DROP PARTITION (year=2024);"


def test_drop_partition_escapes_string_value():
    sch = schema("name")
    p = Partition.of(sch, name="O'Brien")
    ddl = drop_partition_ddl("t", p)
    assert "PARTITION (name='O''Brien')" in ddl


def test_drop_partition_rejects_unsafe_table():
    sch = schema(("year", "int"))
    p = Partition.of(sch, year=2024)
    with pytest.raises(LakeForgeError):
        drop_partition_ddl("t; DROP TABLE x", p)
