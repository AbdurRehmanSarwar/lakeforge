"""Typed partition schemas.

A :class:`PartitionSchema` is an ordered collection of :class:`PartitionColumn`
definitions. Each column knows how to parse a raw string segment (taken from an
S3 key) into a typed Python value, render a typed value back to a string, and
report the equivalent Athena/Glue column type.

Hive-style partition columns are physically strings on disk, but treating
``year``/``month``/``day`` as integers (and dates as ``datetime.date``) makes
partition pruning and DDL generation correct and ergonomic.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any

from .errors import SchemaError


class ColumnType(Enum):
    """Supported partition column types and their Athena equivalents."""

    STRING = "string"
    INT = "int"
    DOUBLE = "double"
    BOOLEAN = "boolean"
    DATE = "date"
    TIMESTAMP = "timestamp"

    @classmethod
    def from_name(cls, name: str) -> ColumnType:
        """Resolve a :class:`ColumnType` from a case-insensitive name.

        Accepts a few common aliases (``str``, ``integer``, ``bigint``,
        ``float``, ``bool``, ``ts``) in addition to the canonical names.
        """
        normalized = name.strip().lower()
        aliases = {
            "str": cls.STRING,
            "integer": cls.INT,
            "bigint": cls.INT,
            "long": cls.INT,
            "float": cls.DOUBLE,
            "bool": cls.BOOLEAN,
            "ts": cls.TIMESTAMP,
            "datetime": cls.TIMESTAMP,
        }
        if normalized in aliases:
            return aliases[normalized]
        try:
            return cls(normalized)
        except ValueError as exc:
            valid = ", ".join(t.value for t in cls)
            raise SchemaError(
                f"unknown column type {name!r}; expected one of: {valid}"
            ) from exc

    @property
    def athena_type(self) -> str:
        """Return the Athena/Glue type string for this column type."""
        return _ATHENA_TYPES[self]


_ATHENA_TYPES = {
    ColumnType.STRING: "string",
    ColumnType.INT: "bigint",
    ColumnType.DOUBLE: "double",
    ColumnType.BOOLEAN: "boolean",
    ColumnType.DATE: "date",
    ColumnType.TIMESTAMP: "timestamp",
}

_TRUE_LITERALS = {"true", "t", "1", "yes", "y"}
_FALSE_LITERALS = {"false", "f", "0", "no", "n"}


@dataclass(frozen=True)
class PartitionColumn:
    """A single typed partition column."""

    name: str
    type: ColumnType = ColumnType.STRING

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise SchemaError("partition column name must be a non-empty string")
        if not isinstance(self.type, ColumnType):
            object.__setattr__(self, "type", ColumnType.from_name(str(self.type)))

    def parse(self, raw: str) -> Any:
        """Parse a raw string path segment into a typed value."""
        try:
            return self._parse(raw)
        except (ValueError, TypeError) as exc:
            raise SchemaError(
                f"cannot parse {raw!r} as {self.type.value} for column {self.name!r}"
            ) from exc

    def _parse(self, raw: str) -> Any:
        if self.type is ColumnType.STRING:
            return raw
        if self.type is ColumnType.INT:
            return int(raw)
        if self.type is ColumnType.DOUBLE:
            return float(raw)
        if self.type is ColumnType.BOOLEAN:
            lowered = raw.strip().lower()
            if lowered in _TRUE_LITERALS:
                return True
            if lowered in _FALSE_LITERALS:
                return False
            raise ValueError(raw)
        if self.type is ColumnType.DATE:
            return date.fromisoformat(raw)
        if self.type is ColumnType.TIMESTAMP:
            return datetime.fromisoformat(raw)
        raise SchemaError(f"unhandled column type {self.type!r}")  # pragma: no cover

    def format(self, value: Any) -> str:
        """Render a typed value as the string used in a partition path."""
        if self.type is ColumnType.BOOLEAN:
            return "true" if value else "false"
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        return str(value)

    @property
    def athena_type(self) -> str:
        """Athena/Glue type for use in DDL (e.g. ``bigint``)."""
        return self.type.athena_type


@dataclass(frozen=True)
class PartitionSchema:
    """An ordered set of partition columns.

    Column *order* is significant: it defines the order of segments in a
    Hive-style partition path (``year=2024/month=01/day=05``).
    """

    columns: tuple[PartitionColumn, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "columns", tuple(self.columns))
        if not self.columns:
            raise SchemaError("a partition schema must define at least one column")
        seen: set[str] = set()
        for column in self.columns:
            if not isinstance(column, PartitionColumn):
                raise SchemaError(f"expected PartitionColumn, got {type(column).__name__}")
            if column.name in seen:
                raise SchemaError(f"duplicate partition column {column.name!r}")
            seen.add(column.name)

    @classmethod
    def of(cls, *specs: Any) -> PartitionSchema:
        """Build a schema from flexible specs.

        Each spec may be a :class:`PartitionColumn`, a plain ``name`` string
        (typed as ``string``), or a ``(name, type)`` pair where ``type`` is a
        :class:`ColumnType` or a type name/alias.

        >>> PartitionSchema.of(("year", "int"), ("month", "int"), "region").names
        ['year', 'month', 'region']
        """
        columns: list[PartitionColumn] = []
        for spec in specs:
            if isinstance(spec, PartitionColumn):
                columns.append(spec)
            elif isinstance(spec, str):
                columns.append(PartitionColumn(spec))
            elif isinstance(spec, tuple) and len(spec) == 2:
                name, type_ = spec
                col_type = type_ if isinstance(type_, ColumnType) else ColumnType.from_name(type_)
                columns.append(PartitionColumn(name, col_type))
            else:
                raise SchemaError(f"invalid column spec: {spec!r}")
        return cls(tuple(columns))

    @classmethod
    def parse(cls, spec: str) -> PartitionSchema:
        """Parse a compact schema spec like ``"year:int,month:int,region"``.

        Columns are comma-separated; an optional ``:type`` suffix sets the type
        (defaulting to ``string``).
        """
        columns: list[PartitionColumn] = []
        for raw in spec.split(","):
            token = raw.strip()
            if not token:
                continue
            if ":" in token:
                name, _, type_name = token.partition(":")
                columns.append(PartitionColumn(name.strip(), ColumnType.from_name(type_name)))
            else:
                columns.append(PartitionColumn(token))
        if not columns:
            raise SchemaError(f"no columns found in schema spec {spec!r}")
        return cls(tuple(columns))

    @property
    def names(self) -> list[str]:
        """Ordered list of column names."""
        return [column.name for column in self.columns]

    def column(self, name: str) -> PartitionColumn:
        """Return the column with ``name`` or raise :class:`SchemaError`."""
        for column in self.columns:
            if column.name == name:
                return column
        raise SchemaError(f"column {name!r} is not in schema {self.names}")

    def has_column(self, name: str) -> bool:
        """Return whether ``name`` is one of the schema's columns."""
        return any(column.name == name for column in self.columns)

    def coerce(self, values: dict[str, Any]) -> dict[str, Any]:
        """Coerce a mapping of raw values to typed values for every column.

        Raises :class:`SchemaError` if a required column is missing or extra
        keys are supplied.
        """
        missing = [name for name in self.names if name not in values]
        if missing:
            raise SchemaError(f"missing values for columns: {missing}")
        extra = [key for key in values if not self.has_column(key)]
        if extra:
            raise SchemaError(f"unexpected columns not in schema: {extra}")
        typed: dict[str, Any] = {}
        for column in self.columns:
            raw = values[column.name]
            typed[column.name] = raw if not isinstance(raw, str) else column.parse(raw)
        return typed

    def __iter__(self) -> Iterator[PartitionColumn]:
        return iter(self.columns)

    def __len__(self) -> int:
        return len(self.columns)


def schema(*specs: Any) -> PartitionSchema:
    """Convenience alias for :meth:`PartitionSchema.of`."""
    return PartitionSchema.of(*specs)


def _ensure_schema(value: PartitionSchema | Iterable[Any] | str) -> PartitionSchema:
    """Normalize loosely-typed schema input into a :class:`PartitionSchema`."""
    if isinstance(value, PartitionSchema):
        return value
    if isinstance(value, str):
        return PartitionSchema.parse(value)
    return PartitionSchema.of(*value)


__all__ = [
    "ColumnType",
    "PartitionColumn",
    "PartitionSchema",
    "schema",
]
