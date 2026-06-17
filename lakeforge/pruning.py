"""Partition pruning.

Given a collection of partitions and a :class:`~lakeforge.predicate.Predicate`,
return only the partitions whose values satisfy the predicate. This is the core
operation that lets a query layer skip scanning irrelevant S3 prefixes.
"""

from __future__ import annotations

from collections.abc import Iterable

from .errors import PredicateError
from .partition import Partition
from .predicate import Predicate
from .schema import PartitionSchema


def validate_predicate(predicate: Predicate, schema: PartitionSchema) -> None:
    """Ensure every column referenced by ``predicate`` exists in ``schema``.

    Raises :class:`PredicateError` if the predicate references unknown columns.
    """
    unknown = sorted(c for c in predicate.columns() if not schema.has_column(c))
    if unknown:
        raise PredicateError(
            f"predicate references columns {unknown} not in schema {schema.names}"
        )


def prune(
    partitions: Iterable[Partition],
    predicate: Predicate,
    *,
    validate: bool = True,
) -> list[Partition]:
    """Return the partitions that satisfy ``predicate``.

    If ``validate`` is true (the default) and the input is non-empty, the
    predicate's columns are checked against the first partition's schema before
    filtering, surfacing typos as a clear :class:`PredicateError`.
    """
    materialized = list(partitions)
    if validate and materialized:
        validate_predicate(predicate, materialized[0].schema)
    return [p for p in materialized if predicate.evaluate(p.values)]


def count_pruned(partitions: Iterable[Partition], predicate: Predicate) -> int:
    """Return how many partitions would be *eliminated* by ``predicate``.

    Useful for logging the selectivity of a prune (e.g. "skipped 340/365
    day partitions").
    """
    materialized = list(partitions)
    kept = prune(materialized, predicate)
    return len(materialized) - len(kept)


__all__ = ["prune", "validate_predicate", "count_pruned"]
