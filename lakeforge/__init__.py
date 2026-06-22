"""lakeforge: tools for Hive-partitioned data lakes on S3.

Public API::

    from lakeforge import (
        PartitionSchema, PartitionColumn, ColumnType, schema,
        Partition, build_partitions,
        Predicate, Eq, Ne, Gt, Ge, Lt, Le, In, Between, And, Or, Not, Always,
        PartitionField, field,
        prune, validate_predicate, count_pruned,
        Manifest, PartitionFiles, build_manifest,
    )

AWS-backed discovery lives in :mod:`lakeforge.discovery` and DDL helpers in
:mod:`lakeforge.glue`.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .errors import (
    DiscoveryError,
    LakeForgeError,
    PartitionError,
    PartitionParseError,
    PredicateError,
    SchemaError,
)
from .generate import date_range, partition_grid
from .manifest import Manifest, PartitionFiles, build_manifest
from .partition import Partition, build_partitions
from .predicate import (
    Always,
    And,
    Between,
    Eq,
    Ge,
    Gt,
    In,
    Le,
    Lt,
    Ne,
    Not,
    Or,
    PartitionField,
    Predicate,
    field,
)
from .pruning import count_pruned, prune, validate_predicate
from .schema import ColumnType, PartitionColumn, PartitionSchema, schema

__all__ = [
    "__version__",
    # schema
    "ColumnType",
    "PartitionColumn",
    "PartitionSchema",
    "schema",
    # partitions
    "Partition",
    "build_partitions",
    # generation
    "date_range",
    "partition_grid",
    # predicates
    "Predicate",
    "Eq",
    "Ne",
    "Gt",
    "Ge",
    "Lt",
    "Le",
    "In",
    "Between",
    "And",
    "Or",
    "Not",
    "Always",
    "PartitionField",
    "field",
    # pruning
    "prune",
    "validate_predicate",
    "count_pruned",
    # manifest
    "Manifest",
    "PartitionFiles",
    "build_manifest",
    # errors
    "LakeForgeError",
    "SchemaError",
    "PartitionError",
    "PartitionParseError",
    "PredicateError",
    "DiscoveryError",
]
