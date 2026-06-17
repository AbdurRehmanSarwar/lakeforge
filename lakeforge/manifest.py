"""Partition manifests.

A :class:`Manifest` records, for a partitioned dataset, which files belong to
which partition. It can be serialized to lakeforge's own JSON layout, or to the
manifest format Amazon Redshift Spectrum / Athena accept for
``CREATE EXTERNAL TABLE ... LOCATION`` with explicit file lists.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from .partition import Partition
from .schema import PartitionSchema


@dataclass
class PartitionFiles:
    """The files that make up a single partition."""

    partition: Partition
    files: list[str] = field(default_factory=list)

    def add(self, *uris: str) -> None:
        """Append one or more file URIs to this partition."""
        self.files.extend(uris)


@dataclass
class Manifest:
    """A mapping of partitions to their files for one dataset/schema."""

    schema: PartitionSchema
    entries: list[PartitionFiles] = field(default_factory=list)

    def add(self, partition: Partition, *files: str) -> PartitionFiles:
        """Add files for ``partition``, merging into an existing entry if present."""
        key = partition.path()
        for entry in self.entries:
            if entry.partition.path() == key:
                entry.add(*files)
                return entry
        entry = PartitionFiles(partition, list(files))
        self.entries.append(entry)
        return entry

    @property
    def total_files(self) -> int:
        """Total number of files across all partitions."""
        return sum(len(entry.files) for entry in self.entries)

    def all_files(self) -> list[str]:
        """Flat list of every file URI in partition order."""
        return [uri for entry in self.entries for uri in entry.files]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to lakeforge's JSON-friendly structure."""
        return {
            "schema": [
                {"name": col.name, "type": col.type.value} for col in self.schema.columns
            ],
            "partitions": [
                {"values": _jsonable(entry.partition.to_dict()), "files": list(entry.files)}
                for entry in self.entries
            ],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        """Serialize the manifest to a JSON string."""
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Manifest:
        """Reconstruct a manifest from :meth:`to_dict` output."""
        schema = PartitionSchema.of(
            *[(col["name"], col["type"]) for col in data["schema"]]
        )
        manifest = cls(schema)
        for record in data["partitions"]:
            partition = Partition(dict(record["values"]), schema)
            manifest.add(partition, *record["files"])
        return manifest

    @classmethod
    def from_json(cls, text: str) -> Manifest:
        """Reconstruct a manifest from a JSON string."""
        return cls.from_dict(json.loads(text))

    def to_redshift_manifest(self, *, mandatory: bool = True) -> str:
        """Render a Redshift Spectrum / Athena style file manifest.

        The format is ``{"entries": [{"url": ..., "mandatory": true}, ...]}``.
        """
        entries = [{"url": uri, "mandatory": mandatory} for uri in self.all_files()]
        return json.dumps({"entries": entries}, indent=2)


def _jsonable(values: dict[str, Any]) -> dict[str, Any]:
    """Convert typed partition values to JSON-serializable forms."""
    out: dict[str, Any] = {}
    for key, value in values.items():
        out[key] = value if isinstance(value, (str, int, float, bool)) else str(value)
    return out


def build_manifest(
    schema: PartitionSchema,
    items: Iterable[tuple[Partition, Iterable[str]]],
) -> Manifest:
    """Build a manifest from ``(partition, files)`` pairs."""
    manifest = Manifest(schema)
    for partition, files in items:
        manifest.add(partition, *files)
    return manifest


__all__ = ["PartitionFiles", "Manifest", "build_manifest"]
