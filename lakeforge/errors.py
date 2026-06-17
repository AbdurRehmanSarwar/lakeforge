"""Exception hierarchy for lakeforge.

All exceptions raised by the library derive from :class:`LakeForgeError`, so
callers can catch everything from the package with a single ``except`` clause.
"""

from __future__ import annotations


class LakeForgeError(Exception):
    """Base class for every error raised by lakeforge."""


class SchemaError(LakeForgeError):
    """Raised when a partition schema is invalid or a value fails to coerce."""


class PartitionError(LakeForgeError):
    """Base class for partition-related errors."""


class PartitionParseError(PartitionError):
    """Raised when a string cannot be parsed into a partition for a schema."""


class PredicateError(LakeForgeError):
    """Raised when a predicate references unknown columns or is malformed."""


class DiscoveryError(LakeForgeError):
    """Raised when S3 partition discovery cannot be performed."""


__all__ = [
    "LakeForgeError",
    "SchemaError",
    "PartitionError",
    "PartitionParseError",
    "PredicateError",
    "DiscoveryError",
]
