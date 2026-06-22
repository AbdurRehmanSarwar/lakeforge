"""Athena / AWS Glue DDL generation.

Pure string builders for the SQL most often needed when registering
Hive-partitioned data in the Glue Data Catalog and querying it with Athena:

* ``CREATE EXTERNAL TABLE`` statements
* ``ALTER TABLE ... ADD PARTITION`` statements
* ``MSCK REPAIR TABLE``
* Athena *partition projection* table properties

These functions never touch AWS; they return SQL strings you can run with
``boto3`` (Athena ``StartQueryExecution``) or any SQL client.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from .errors import LakeForgeError, SchemaError
from .partition import Partition
from .schema import ColumnType, PartitionColumn, PartitionSchema

# Column types whose partition values must be quoted as string literals in DDL.
_QUOTED_TYPES = {ColumnType.STRING, ColumnType.DATE, ColumnType.TIMESTAMP, ColumnType.BOOLEAN}

# Athena/Hive identifiers we are willing to interpolate into DDL unquoted.
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _quote(text: object) -> str:
    """Wrap a value in single quotes, doubling embedded quotes for SQL safety."""
    return "'" + str(text).replace("'", "''") + "'"


def _validate_identifier(name: str, kind: str = "identifier") -> str:
    """Validate a table/database/column identifier before it enters DDL.

    Identifiers are interpolated into SQL unquoted, so they must be restricted
    to a safe character set to avoid injection. Raises :class:`LakeForgeError`.
    """
    if not isinstance(name, str) or not _IDENTIFIER_RE.match(name):
        raise LakeForgeError(
            f"invalid {kind} {name!r}: expected letters, digits and underscores, "
            "not starting with a digit"
        )
    return name


def _qualified(table: str, database: str | None) -> str:
    _validate_identifier(table, "table name")
    if database is not None:
        _validate_identifier(database, "database name")
        return f"{database}.{table}"
    return table


def _sql_literal(column: PartitionColumn, value: object) -> str:
    """Render a partition value as a SQL literal for a PARTITION clause."""
    if column.type in _QUOTED_TYPES:
        return _quote(column.format(value))
    # INT/DOUBLE are emitted unquoted; guard the runtime type so a non-numeric
    # native value cannot inject arbitrary text into the statement.
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise SchemaError(
            f"column {column.name!r} ({column.type.value}) expects a numeric value, "
            f"got {type(value).__name__}"
        )
    return column.format(value)


def add_partition_ddl(
    table: str,
    partition: Partition,
    location_base: str,
    *,
    database: str | None = None,
    if_not_exists: bool = True,
) -> str:
    """Build an ``ALTER TABLE ... ADD PARTITION`` statement.

    >>> from lakeforge import schema, Partition
    >>> from lakeforge.glue import add_partition_ddl
    >>> p = Partition.of(schema(("year", "int"), "region"), year=2024, region="us")
    >>> add_partition_ddl("events", p, "s3://bucket/events")
    "ALTER TABLE events ADD IF NOT EXISTS PARTITION (year=2024, region='us') LOCATION 's3://bucket/events/year=2024/region=us/';"
    """
    spec = ", ".join(
        f"{_validate_identifier(col.name, 'partition column name')}="
        f"{_sql_literal(col, partition.values[col.name])}"
        for col in partition.schema.columns
    )
    location = partition.s3_uri(location_base, trailing_slash=True)
    guard = "IF NOT EXISTS " if if_not_exists else ""
    return (
        f"ALTER TABLE {_qualified(table, database)} ADD {guard}"
        f"PARTITION ({spec}) LOCATION '{location}';"
    )


def add_partitions_ddl(
    table: str,
    partitions: Iterable[Partition],
    location_base: str,
    *,
    database: str | None = None,
    if_not_exists: bool = True,
) -> str:
    """Build a single ``ALTER TABLE ... ADD`` with multiple PARTITION clauses.

    Athena allows adding many partitions in one statement, which is far faster
    than issuing one statement per partition.
    """
    clauses = []
    table_ref = _qualified(table, database)
    for partition in partitions:
        spec = ", ".join(
            f"{_validate_identifier(col.name, 'partition column name')}="
            f"{_sql_literal(col, partition.values[col.name])}"
            for col in partition.schema.columns
        )
        location = partition.s3_uri(location_base, trailing_slash=True)
        clauses.append(f"  PARTITION ({spec}) LOCATION '{location}'")
    if not clauses:
        raise ValueError("add_partitions_ddl requires at least one partition")
    guard = "IF NOT EXISTS\n" if if_not_exists else "\n"
    return f"ALTER TABLE {table_ref} ADD {guard}" + "\n".join(clauses) + ";"


def drop_partition_ddl(
    table: str,
    partition: Partition,
    *,
    database: str | None = None,
    if_exists: bool = True,
) -> str:
    """Build an ``ALTER TABLE ... DROP PARTITION`` statement.

    Useful for retiring or rewriting a partition; pair with
    :func:`add_partition_ddl` to atomically re-point a partition's location.
    """
    spec = ", ".join(
        f"{_validate_identifier(col.name, 'partition column name')}="
        f"{_sql_literal(col, partition.values[col.name])}"
        for col in partition.schema.columns
    )
    guard = "IF EXISTS " if if_exists else ""
    return f"ALTER TABLE {_qualified(table, database)} DROP {guard}PARTITION ({spec});"


def create_table_ddl(
    table: str,
    columns: Mapping[str, str],
    partition_schema: PartitionSchema,
    location: str,
    *,
    database: str | None = None,
    stored_as: str = "PARQUET",
    if_not_exists: bool = True,
    table_properties: Mapping[str, str] | None = None,
) -> str:
    """Build a ``CREATE EXTERNAL TABLE`` statement.

    ``columns`` maps (non-partition) column names to their Athena types. The
    partition columns come from ``partition_schema`` and are emitted in a
    ``PARTITIONED BY`` clause (Athena requires they not also appear in the main
    column list).
    """
    overlap = [name for name in columns if partition_schema.has_column(name)]
    if overlap:
        raise ValueError(
            f"columns {overlap} appear in both the table body and partition schema; "
            "partition columns must only be declared in PARTITIONED BY"
        )

    guard = "IF NOT EXISTS " if if_not_exists else ""
    col_lines = ",\n".join(
        f"  {_validate_identifier(name, 'column name')} {dtype}"
        for name, dtype in columns.items()
    )
    part_cols = ", ".join(
        f"{_validate_identifier(col.name, 'partition column name')} {col.athena_type}"
        for col in partition_schema.columns
    )
    normalized_location = location.rstrip("/") + "/"

    parts = [
        f"CREATE EXTERNAL TABLE {guard}{_qualified(table, database)} (",
        col_lines,
        f") PARTITIONED BY ({part_cols})",
        f"STORED AS {stored_as}",
        f"LOCATION '{normalized_location}'",
    ]
    if table_properties:
        rendered = ", ".join(f"{_quote(k)}={_quote(v)}" for k, v in table_properties.items())
        parts.append(f"TBLPROPERTIES ({rendered})")
    return "\n".join(parts) + ";"


def msck_repair(table: str, *, database: str | None = None) -> str:
    """Build a ``MSCK REPAIR TABLE`` statement to discover existing partitions."""
    return f"MSCK REPAIR TABLE {_qualified(table, database)};"


def projection_properties(
    partition_schema: PartitionSchema,
    location_template: str,
    *,
    ranges: Mapping[str, tuple[object, object]] | None = None,
    digits: Mapping[str, int] | None = None,
    enum_values: Mapping[str, Iterable[str]] | None = None,
    interval: Mapping[str, int] | None = None,
) -> dict[str, str]:
    """Build Athena *partition projection* table properties.

    Partition projection lets Athena compute partition locations from the query
    instead of listing them in the catalog, which is much faster for large,
    regular partition layouts. The returned dict is suitable for the
    ``table_properties`` argument of :func:`create_table_ddl`.

    * Integer columns project as ``type=integer`` over the provided ``ranges``.
    * Date/timestamp columns project as ``type=date``.
    * String columns project as ``type=enum`` using ``enum_values``.
    """
    ranges = ranges or {}
    digits = digits or {}
    enum_values = enum_values or {}
    interval = interval or {}

    props: dict[str, str] = {
        "projection.enabled": "true",
        "storage.location.template": location_template,
    }
    for column in partition_schema.columns:
        prefix = f"projection.{column.name}"
        if column.type is ColumnType.INT:
            if column.name not in ranges:
                raise ValueError(f"integer projection for {column.name!r} requires a range")
            low, high = ranges[column.name]
            props[f"{prefix}.type"] = "integer"
            props[f"{prefix}.range"] = f"{low},{high}"
            if column.name in interval:
                props[f"{prefix}.interval"] = str(interval[column.name])
            if column.name in digits:
                props[f"{prefix}.digits"] = str(digits[column.name])
        elif column.type in (ColumnType.DATE, ColumnType.TIMESTAMP):
            if column.name not in ranges:
                raise ValueError(f"date projection for {column.name!r} requires a range")
            low, high = ranges[column.name]
            props[f"{prefix}.type"] = "date"
            props[f"{prefix}.range"] = f"{low},{high}"
            props[f"{prefix}.format"] = (
                "yyyy-MM-dd" if column.type is ColumnType.DATE else "yyyy-MM-dd'T'HH:mm:ss"
            )
        else:
            values = enum_values.get(column.name)
            if not values:
                raise ValueError(
                    f"string projection for {column.name!r} requires enum_values"
                )
            props[f"{prefix}.type"] = "enum"
            props[f"{prefix}.values"] = ",".join(values)
    return props


__all__ = [
    "add_partition_ddl",
    "add_partitions_ddl",
    "drop_partition_ddl",
    "create_table_ddl",
    "msck_repair",
    "projection_properties",
]
