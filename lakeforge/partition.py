"""Hive-style partitions and partition paths.

A :class:`Partition` binds a set of typed column values to a
:class:`~lakeforge.schema.PartitionSchema`. It can render a Hive-style path
(``year=2024/month=01/day=05``), build a full S3 URI, and be parsed back from a
path or S3 key.

Path *segment values* are percent-encoded so that arbitrary string values
(spaces, slashes, ``=``) round-trip safely.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, unquote

from .errors import PartitionParseError
from .schema import PartitionSchema, _ensure_schema

# Characters that are safe to leave unescaped inside a partition segment value.
# Everything else (including "/" and "=") is percent-encoded.
_SAFE_SEGMENT_CHARS = "-_.:"


def _encode(value: str) -> str:
    return quote(value, safe=_SAFE_SEGMENT_CHARS)


def _decode(value: str) -> str:
    return unquote(value)


@dataclass(frozen=True)
class Partition:
    """A concrete partition: typed values for every column in a schema."""

    values: Mapping[str, Any]
    schema: PartitionSchema

    def __post_init__(self) -> None:
        # Re-key the values dict in schema order with typed values, validating
        # presence/extra keys via the schema.
        typed = self.schema.coerce(dict(self.values))
        ordered = {name: typed[name] for name in self.schema.names}
        object.__setattr__(self, "values", ordered)

    @classmethod
    def of(cls, schema: PartitionSchema, /, **values: Any) -> Partition:
        """Construct a partition from keyword values.

        ``schema`` is positional-only so it never collides with a partition
        column literally named ``schema``.

        >>> from lakeforge import schema, Partition
        >>> s = schema(("year", "int"), ("month", "int"))
        >>> Partition.of(s, year=2024, month=1).path()
        'year=2024/month=1'
        """
        return cls(values, schema)

    def path(self, *, encode: bool = True, trailing_slash: bool = False) -> str:
        """Render the Hive-style partition path (no leading slash).

        Integer columns render without zero-padding (``month=1``). For
        zero-padded segments such as ``month=01`` declare the column as a
        ``string`` and pass ``"01"``.

        >>> from lakeforge import schema, Partition
        >>> p = Partition.of(schema(("year", "int"), ("month", "int")), year=2024, month=1)
        >>> p.path()
        'year=2024/month=1'
        """
        segments = []
        for column in self.schema.columns:
            rendered = column.format(self.values[column.name])
            if encode:
                rendered = _encode(rendered)
            segments.append(f"{column.name}={rendered}")
        path = "/".join(segments)
        return path + "/" if trailing_slash else path

    def s3_uri(self, base: str, *, trailing_slash: bool = True) -> str:
        """Join this partition path onto a base location (S3 URI or prefix)."""
        normalized = base.rstrip("/")
        return f"{normalized}/{self.path(trailing_slash=trailing_slash)}"

    @classmethod
    def parse(cls, path: str, schema: PartitionSchema | str | Iterable[Any]) -> Partition:
        """Parse a Hive-style partition path into a :class:`Partition`.

        Accepts a bare partition path (``year=2024/month=01``), a path with
        leading/trailing slashes, or a full S3 key/URI that *contains* the
        partition path (any leading prefix and trailing filename are ignored).
        """
        resolved = _ensure_schema(schema)
        wanted = set(resolved.names)
        found: dict[str, str] = {}
        for segment in path.split("/"):
            if "=" not in segment:
                continue
            key, _, raw_value = segment.partition("=")
            key = key.strip()
            if key in wanted and key not in found:
                found[key] = _decode(raw_value)
        missing = [name for name in resolved.names if name not in found]
        if missing:
            raise PartitionParseError(
                f"path {path!r} is missing partition columns {missing} "
                f"for schema {resolved.names}"
            )
        typed = {name: resolved.column(name).parse(found[name]) for name in resolved.names}
        return cls(typed, resolved)

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dict of typed values in schema order."""
        return dict(self.values)

    def __getitem__(self, key: str) -> Any:
        return self.values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.values)

    def __len__(self) -> int:
        return len(self.values)


def build_partitions(
    schema: PartitionSchema,
    rows: Any,
) -> list[Partition]:
    """Build a list of partitions from an iterable of value mappings.

    Each row is a mapping of column name to value (raw strings or typed
    values). Useful for turning query results or config into partitions.
    """
    return [Partition(dict(row), schema) for row in rows]


__all__ = ["Partition", "build_partitions"]
