"""Enumerate partitions for backfills and batch registration.

When you backfill a date-partitioned table or register many partitions at once,
you need the *set* of partitions to operate on. :func:`date_range` produces the
dates, and :func:`partition_grid` builds the cartesian product of partitions
from per-column value lists.
"""

from __future__ import annotations

import calendar
from collections.abc import Iterable
from datetime import date, timedelta
from itertools import product
from typing import Any

from .errors import LakeForgeError
from .partition import Partition
from .schema import PartitionSchema

_STEPS = ("day", "month", "year")


def _days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _stepped(start: date, index: int, step: str) -> date:
    """The date ``index`` steps after ``start``, anchored on the start day.

    The day-of-month is taken from ``start`` each time (not the previous step),
    clamped to the target month's length, so it never drifts.
    """
    if step == "day":
        return start + timedelta(days=index)
    if step == "month":
        total = (start.month - 1) + index
        year = start.year + total // 12
        month = total % 12 + 1
    else:  # year
        year = start.year + index
        month = start.month
    return date(year, month, min(start.day, _days_in_month(year, month)))


def date_range(start: date, end: date, step: str = "day") -> list[date]:
    """Return the inclusive list of dates from ``start`` to ``end``.

    ``step`` is one of ``"day"``, ``"month"``, or ``"year"``. For month/year
    steps the day-of-month is anchored on ``start`` and clamped to each target
    month's length (so stepping monthly from Jan 31 yields Feb 28/29, Mar 31, …).
    """
    if step not in _STEPS:
        raise LakeForgeError(f"step must be one of {_STEPS}, got {step!r}")
    if end < start:
        raise LakeForgeError("end must be on or after start")
    out: list[date] = []
    index = 0
    while True:
        current = _stepped(start, index, step)
        if current > end:
            break
        out.append(current)
        index += 1
    return out


def partition_grid(schema: PartitionSchema, **columns: Iterable[Any]) -> list[Partition]:
    """Build the cartesian product of partitions from per-column value lists.

    Every schema column must be supplied as a keyword whose value is an iterable
    of values; partitions are emitted in schema column order.

    >>> from lakeforge import schema
    >>> parts = partition_grid(schema(("year", "int"), "region"), year=[2024], region=["us", "eu"])
    >>> [p.path() for p in parts]
    ['year=2024/region=us', 'year=2024/region=eu']
    """
    names = schema.names
    missing = [name for name in names if name not in columns]
    if missing:
        raise LakeForgeError(f"missing values for columns: {missing}")
    extra = [key for key in columns if not schema.has_column(key)]
    if extra:
        raise LakeForgeError(f"unknown columns not in schema: {extra}")
    value_lists = [list(columns[name]) for name in names]
    return [
        Partition(dict(zip(names, combo)), schema)
        for combo in product(*value_lists)
    ]


__all__ = ["date_range", "partition_grid"]
