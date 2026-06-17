"""Predicates for partition pruning.

Predicates describe a filter over partition column values. They can be combined
with ``&`` (AND), ``|`` (OR) and ``~`` (NOT), and evaluated against a mapping of
typed partition values.

Two equivalent styles are supported::

    # explicit
    pred = And(Ge("year", 2023), In("region", ["us", "eu"]))

    # fluent DSL
    pred = (field("year") >= 2023) & field("region").isin(["us", "eu"])
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


class Predicate(ABC):
    """Abstract base class for partition predicates."""

    @abstractmethod
    def evaluate(self, values: Mapping[str, Any]) -> bool:
        """Return whether ``values`` satisfy this predicate."""

    @abstractmethod
    def columns(self) -> set[str]:
        """Return the set of column names referenced by this predicate."""

    def __and__(self, other: Predicate) -> Predicate:
        return And(self, other)

    def __or__(self, other: Predicate) -> Predicate:
        return Or(self, other)

    def __invert__(self) -> Predicate:
        return Not(self)


@dataclass(frozen=True)
class _Comparison(Predicate):
    column: str
    value: Any

    def columns(self) -> set[str]:
        return {self.column}


class Eq(_Comparison):
    """``column == value``"""

    def evaluate(self, values: Mapping[str, Any]) -> bool:
        return bool(values[self.column] == self.value)


class Ne(_Comparison):
    """``column != value``"""

    def evaluate(self, values: Mapping[str, Any]) -> bool:
        return bool(values[self.column] != self.value)


class Gt(_Comparison):
    """``column > value``"""

    def evaluate(self, values: Mapping[str, Any]) -> bool:
        return bool(values[self.column] > self.value)


class Ge(_Comparison):
    """``column >= value``"""

    def evaluate(self, values: Mapping[str, Any]) -> bool:
        return bool(values[self.column] >= self.value)


class Lt(_Comparison):
    """``column < value``"""

    def evaluate(self, values: Mapping[str, Any]) -> bool:
        return bool(values[self.column] < self.value)


class Le(_Comparison):
    """``column <= value``"""

    def evaluate(self, values: Mapping[str, Any]) -> bool:
        return bool(values[self.column] <= self.value)


@dataclass(frozen=True)
class In(Predicate):
    """``column in values``"""

    column: str
    values: tuple[Any, ...]

    def __init__(self, column: str, values: Iterable[Any]) -> None:
        object.__setattr__(self, "column", column)
        object.__setattr__(self, "values", tuple(values))

    def evaluate(self, values: Mapping[str, Any]) -> bool:
        return values[self.column] in self.values

    def columns(self) -> set[str]:
        return {self.column}


@dataclass(frozen=True)
class Between(Predicate):
    """``low <= column <= high`` (inclusive on both ends)."""

    column: str
    low: Any
    high: Any

    def evaluate(self, values: Mapping[str, Any]) -> bool:
        return bool(self.low <= values[self.column] <= self.high)

    def columns(self) -> set[str]:
        return {self.column}


@dataclass(frozen=True)
class And(Predicate):
    """Logical AND of one or more predicates (empty AND is always true)."""

    parts: tuple[Predicate, ...]

    def __init__(self, *parts: Predicate) -> None:
        object.__setattr__(self, "parts", tuple(parts))

    def evaluate(self, values: Mapping[str, Any]) -> bool:
        return all(part.evaluate(values) for part in self.parts)

    def columns(self) -> set[str]:
        return set().union(*(part.columns() for part in self.parts)) if self.parts else set()


@dataclass(frozen=True)
class Or(Predicate):
    """Logical OR of one or more predicates (empty OR is always false)."""

    parts: tuple[Predicate, ...]

    def __init__(self, *parts: Predicate) -> None:
        object.__setattr__(self, "parts", tuple(parts))

    def evaluate(self, values: Mapping[str, Any]) -> bool:
        return any(part.evaluate(values) for part in self.parts)

    def columns(self) -> set[str]:
        return set().union(*(part.columns() for part in self.parts)) if self.parts else set()


@dataclass(frozen=True)
class Not(Predicate):
    """Logical negation of a predicate."""

    inner: Predicate

    def evaluate(self, values: Mapping[str, Any]) -> bool:
        return not self.inner.evaluate(values)

    def columns(self) -> set[str]:
        return self.inner.columns()


@dataclass(frozen=True)
class Always(Predicate):
    """Predicate that matches every partition."""

    def evaluate(self, values: Mapping[str, Any]) -> bool:
        return True

    def columns(self) -> set[str]:
        return set()


class PartitionField:
    """Fluent builder that produces predicates via comparison operators.

    Created with :func:`field`. Comparison operators return predicate
    instances rather than booleans, enabling expressions like
    ``field("year") >= 2023``.
    """

    __hash__ = None  # type: ignore[assignment]

    def __init__(self, name: str) -> None:
        self.name = name

    def __eq__(self, value: object) -> Predicate:  # type: ignore[override]
        return Eq(self.name, value)

    def __ne__(self, value: object) -> Predicate:  # type: ignore[override]
        return Ne(self.name, value)

    def __gt__(self, value: Any) -> Predicate:
        return Gt(self.name, value)

    def __ge__(self, value: Any) -> Predicate:
        return Ge(self.name, value)

    def __lt__(self, value: Any) -> Predicate:
        return Lt(self.name, value)

    def __le__(self, value: Any) -> Predicate:
        return Le(self.name, value)

    def isin(self, values: Iterable[Any]) -> Predicate:
        """``column in values``"""
        return In(self.name, values)

    def between(self, low: Any, high: Any) -> Predicate:
        """``low <= column <= high``"""
        return Between(self.name, low, high)


def field(name: str) -> PartitionField:
    """Start a fluent predicate for column ``name``."""
    return PartitionField(name)


__all__ = [
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
]
