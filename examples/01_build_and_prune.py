"""Build a set of Hive-style partitions and prune them with a predicate.

This example defines a ``year`` / ``month`` / ``region`` partition schema,
builds a small grid of partitions with :func:`lakeforge.build_partitions`, then
filters them down with a predicate using :func:`lakeforge.prune`.

It shows both predicate styles supported by lakeforge:

* the fluent DSL (``field("year") >= 2024``)
* the explicit constructors (``Ge``, ``In``, ``And``)

Run it with::

    python examples/01_build_and_prune.py
"""

from __future__ import annotations

from itertools import product

from lakeforge import (
    And,
    Ge,
    In,
    build_partitions,
    count_pruned,
    field,
    prune,
    schema,
)


def main() -> None:
    # year and month are integers, region is a (default) string column. Column
    # order is significant: it defines the order of segments in the partition
    # path, e.g. ``year=2024/month=1/region=us``.
    part_schema = schema(("year", "int"), ("month", "int"), "region")
    print("Schema columns:", part_schema.names)

    # Build the cartesian product of years x months x regions as raw rows, then
    # turn each row into a typed Partition.
    years = [2023, 2024]
    months = [1, 2, 3]
    regions = ["us", "eu", "apac"]
    rows = [
        {"year": y, "month": m, "region": r}
        for y, m, r in product(years, months, regions)
    ]
    partitions = build_partitions(part_schema, rows)
    print(f"Built {len(partitions)} partitions total.")

    # Predicate via the fluent DSL: 2024 data for the us/eu regions only.
    fluent = (field("year") >= 2024) & field("region").isin(["us", "eu"])

    # The exact same predicate written with explicit constructors.
    explicit = And(Ge("year", 2024), In("region", ["us", "eu"]))

    kept = prune(partitions, fluent)
    eliminated = count_pruned(partitions, explicit)

    print(f"\nPredicate: year >= 2024 AND region in (us, eu)")
    print(f"Kept {len(kept)} partitions, pruned {eliminated}.")
    print("\nKept partitions:")
    for partition in kept:
        print(f"  {partition.path()}  ->  values={partition.to_dict()}")


if __name__ == "__main__":
    main()
