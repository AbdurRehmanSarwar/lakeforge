"""Generate Athena / AWS Glue DDL for a Hive-partitioned dataset.

This example uses :mod:`lakeforge.glue` to build, as plain SQL strings:

* a ``CREATE EXTERNAL TABLE`` statement (with a ``PARTITIONED BY`` clause)
* an ``ALTER TABLE ... ADD PARTITION`` statement for a concrete partition
* a batched ``ALTER TABLE ... ADD`` with multiple partitions
* Athena *partition projection* ``TBLPROPERTIES``, then a second
  ``CREATE EXTERNAL TABLE`` that embeds those properties

None of these functions touch AWS; they only return SQL you could later run
via Athena ``StartQueryExecution`` or any SQL client.

Run it with::

    python examples/02_athena_ddl.py
"""

from __future__ import annotations

from lakeforge import Partition, build_partitions, schema
from lakeforge.glue import (
    add_partition_ddl,
    add_partitions_ddl,
    create_table_ddl,
    projection_properties,
)


def banner(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def main() -> None:
    # year/month are integers; region is a string column.
    part_schema = schema(("year", "int"), ("month", "int"), "region")
    location = "s3://example-data-lake/events"

    # Non-partition (table body) columns mapped to their Athena types.
    columns = {
        "event_id": "string",
        "user_id": "bigint",
        "amount": "double",
    }

    banner("CREATE EXTERNAL TABLE")
    create_sql = create_table_ddl(
        "events",
        columns,
        part_schema,
        location,
        database="analytics",
        stored_as="PARQUET",
    )
    print(create_sql)

    banner("ALTER TABLE ... ADD PARTITION (single)")
    one = Partition.of(part_schema, year=2024, month=6, region="us")
    print(add_partition_ddl("events", one, location, database="analytics"))

    banner("ALTER TABLE ... ADD PARTITION (batched)")
    rows = [
        {"year": 2024, "month": 6, "region": "us"},
        {"year": 2024, "month": 6, "region": "eu"},
        {"year": 2024, "month": 7, "region": "us"},
    ]
    many = build_partitions(part_schema, rows)
    print(add_partitions_ddl("events", many, location, database="analytics"))

    banner("Partition projection TBLPROPERTIES")
    # Integer columns need a numeric range; string columns need enum values.
    props = projection_properties(
        part_schema,
        location_template=(
            f"{location}/year=${{year}}/month=${{month}}/region=${{region}}"
        ),
        ranges={"year": (2020, 2030), "month": (1, 12)},
        digits={"month": 2},
        enum_values={"region": ["us", "eu", "apac"]},
    )
    for key, value in props.items():
        print(f"  {key} = {value}")

    banner("CREATE EXTERNAL TABLE with partition projection")
    projected_sql = create_table_ddl(
        "events_projected",
        columns,
        part_schema,
        location,
        database="analytics",
        table_properties=props,
    )
    print(projected_sql)


if __name__ == "__main__":
    main()
