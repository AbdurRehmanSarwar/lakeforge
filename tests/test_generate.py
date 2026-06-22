"""Tests for :mod:`lakeforge.generate`."""

from __future__ import annotations

from datetime import date

import pytest

from lakeforge import date_range, partition_grid, schema
from lakeforge.errors import LakeForgeError


def test_date_range_daily_inclusive():
    assert date_range(date(2024, 1, 1), date(2024, 1, 4)) == [
        date(2024, 1, 1),
        date(2024, 1, 2),
        date(2024, 1, 3),
        date(2024, 1, 4),
    ]


def test_date_range_single_day():
    assert date_range(date(2024, 1, 1), date(2024, 1, 1)) == [date(2024, 1, 1)]


def test_date_range_monthly():
    assert date_range(date(2024, 1, 15), date(2024, 4, 15), "month") == [
        date(2024, 1, 15),
        date(2024, 2, 15),
        date(2024, 3, 15),
        date(2024, 4, 15),
    ]


def test_date_range_monthly_anchors_day_without_drift():
    # Jan 31 -> Feb 29 (leap) -> Mar 31 -> Apr 30: day anchors on 31, clamped.
    assert date_range(date(2024, 1, 31), date(2024, 4, 30), "month") == [
        date(2024, 1, 31),
        date(2024, 2, 29),
        date(2024, 3, 31),
        date(2024, 4, 30),
    ]


def test_date_range_crosses_year_boundary_monthly():
    assert date_range(date(2023, 11, 1), date(2024, 2, 1), "month") == [
        date(2023, 11, 1),
        date(2023, 12, 1),
        date(2024, 1, 1),
        date(2024, 2, 1),
    ]


def test_date_range_yearly():
    assert date_range(date(2020, 6, 1), date(2023, 6, 1), "year") == [
        date(2020, 6, 1),
        date(2021, 6, 1),
        date(2022, 6, 1),
        date(2023, 6, 1),
    ]


def test_date_range_yearly_leap_day_clamps():
    assert date_range(date(2020, 2, 29), date(2021, 2, 28), "year") == [
        date(2020, 2, 29),
        date(2021, 2, 28),
    ]


def test_date_range_invalid_step():
    with pytest.raises(LakeForgeError):
        date_range(date(2024, 1, 1), date(2024, 1, 2), "week")


def test_date_range_end_before_start():
    with pytest.raises(LakeForgeError):
        date_range(date(2024, 1, 2), date(2024, 1, 1))


def test_partition_grid_cartesian_product():
    sch = schema(("year", "int"), "region")
    parts = partition_grid(sch, year=[2023, 2024], region=["us", "eu"])
    assert [p.path() for p in parts] == [
        "year=2023/region=us",
        "year=2023/region=eu",
        "year=2024/region=us",
        "year=2024/region=eu",
    ]


def test_partition_grid_follows_schema_order_not_kwarg_order():
    sch = schema("region", ("year", "int"))
    parts = partition_grid(sch, year=[2024], region=["us"])
    assert parts[0].path() == "region=us/year=2024"


def test_partition_grid_values_are_typed():
    sch = schema(("year", "int"))
    parts = partition_grid(sch, year=[2024])
    assert parts[0]["year"] == 2024


def test_partition_grid_empty_values_yields_no_partitions():
    sch = schema(("year", "int"), "region")
    assert partition_grid(sch, year=[], region=["us"]) == []


def test_partition_grid_missing_column():
    sch = schema(("year", "int"), "region")
    with pytest.raises(LakeForgeError):
        partition_grid(sch, year=[2024])


def test_partition_grid_unknown_column():
    sch = schema(("year", "int"))
    with pytest.raises(LakeForgeError):
        partition_grid(sch, year=[2024], month=[1])
