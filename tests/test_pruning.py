"""Tests for :mod:`lakeforge.pruning`.

Covers ``prune`` (filtering and validation behaviour), ``validate_predicate``
(unknown-column detection) and ``count_pruned`` (elimination count). Real
:class:`Partition` objects are built from a real :class:`PartitionSchema`.
"""

from __future__ import annotations

import pytest

from lakeforge.errors import PredicateError
from lakeforge.partition import Partition
from lakeforge.predicate import Always, And, Eq, In, Not, field
from lakeforge.pruning import count_pruned, prune, validate_predicate
from lakeforge.schema import PartitionSchema


def make_schema() -> PartitionSchema:
    return PartitionSchema.of(("year", "int"), ("month", "int"), "region")


def make_partitions(schema: PartitionSchema) -> list[Partition]:
    rows = [
        {"year": 2024, "month": 1, "region": "us"},
        {"year": 2024, "month": 2, "region": "eu"},
        {"year": 2023, "month": 1, "region": "us"},
        {"year": 2023, "month": 12, "region": "eu"},
    ]
    return [Partition(row, schema) for row in rows]


@pytest.fixture
def schema() -> PartitionSchema:
    return make_schema()


@pytest.fixture
def partitions(schema: PartitionSchema) -> list[Partition]:
    return make_partitions(schema)


# --------------------------------------------------------------------------
# prune: keeps only matching partitions
# --------------------------------------------------------------------------

def test_prune_keeps_only_matching_partitions(partitions):
    kept = prune(partitions, Eq("year", 2024))
    assert len(kept) == 2
    assert all(p["year"] == 2024 for p in kept)
    assert {p["region"] for p in kept} == {"us", "eu"}


def test_prune_preserves_input_order(partitions):
    kept = prune(partitions, Eq("region", "us"))
    # us partitions are the 1st and 3rd of the input, in that order.
    assert [p["year"] for p in kept] == [2024, 2023]


def test_prune_returns_list(partitions):
    kept = prune(partitions, Always())
    assert isinstance(kept, list)


def test_prune_always_keeps_everything(partitions):
    kept = prune(partitions, Always())
    assert len(kept) == len(partitions)
    assert kept == partitions


def test_prune_no_match_returns_empty(partitions):
    kept = prune(partitions, Eq("year", 1999))
    assert kept == []


def test_prune_compound_predicate(partitions):
    pred = And(Eq("year", 2024), In("region", ["us"]))
    kept = prune(partitions, pred)
    assert len(kept) == 1
    assert kept[0]["year"] == 2024
    assert kept[0]["region"] == "us"


def test_prune_fluent_predicate(partitions):
    pred = (field("year") >= 2024) & field("region").isin(["us", "eu"])
    kept = prune(partitions, pred)
    assert {p["region"] for p in kept} == {"us", "eu"}
    assert all(p["year"] >= 2024 for p in kept)


def test_prune_not_predicate(partitions):
    kept = prune(partitions, Not(Eq("region", "us")))
    assert all(p["region"] != "us" for p in kept)
    assert len(kept) == 2


def test_prune_does_not_mutate_input(partitions):
    original = list(partitions)
    prune(partitions, Eq("year", 2024))
    assert partitions == original


def test_prune_accepts_arbitrary_iterable(schema):
    rows = make_partitions(schema)
    # A generator is a single-use iterable; prune must materialize it.
    kept = prune((p for p in rows), Eq("year", 2024))
    assert len(kept) == 2


# --------------------------------------------------------------------------
# validate_predicate
# --------------------------------------------------------------------------

def test_validate_predicate_passes_for_known_columns(schema):
    # Returns None and does not raise for a valid predicate.
    assert validate_predicate(Eq("year", 2024), schema) is None


def test_validate_predicate_raises_for_unknown_column(schema):
    with pytest.raises(PredicateError):
        validate_predicate(Eq("continent", "europe"), schema)


def test_validate_predicate_error_lists_unknown_columns_sorted(schema):
    pred = And(field("zoo") == 1, field("apex") == 2)
    with pytest.raises(PredicateError) as exc:
        validate_predicate(pred, schema)
    message = str(exc.value)
    # Unknown columns are reported sorted.
    assert "['apex', 'zoo']" in message
    # Known column should not appear in the unknown list.
    assert "year" not in message.split("not in schema")[0]


def test_validate_predicate_known_column_in_compound_does_not_raise(schema):
    # All referenced columns exist -> no error.
    pred = And(Eq("year", 2024), Eq("region", "us"))
    assert validate_predicate(pred, schema) is None


def test_validate_predicate_always_has_no_columns(schema):
    # Always references no columns, so validation is trivially satisfied.
    assert validate_predicate(Always(), schema) is None


# --------------------------------------------------------------------------
# prune validation behaviour
# --------------------------------------------------------------------------

def test_prune_validates_by_default(partitions):
    with pytest.raises(PredicateError):
        prune(partitions, Eq("continent", "europe"))


def test_prune_validate_false_skips_check(partitions):
    # With validate=False the unknown-column check is skipped. Eq.evaluate then
    # does values[self.column], which raises KeyError for the missing column.
    with pytest.raises(KeyError):
        prune(partitions, Eq("continent", "europe"), validate=False)


def test_prune_validate_false_filters_normally(partitions):
    # validate=False still filters correctly when the predicate is valid.
    kept = prune(partitions, Eq("year", 2024), validate=False)
    assert len(kept) == 2
    assert all(p["year"] == 2024 for p in kept)


# --------------------------------------------------------------------------
# empty input
# --------------------------------------------------------------------------

def test_prune_empty_input_returns_empty():
    assert prune([], Eq("year", 2024)) == []


def test_prune_empty_input_skips_validation():
    # With no partitions there is no schema to validate against, so even an
    # invalid predicate does not raise; the result is just empty.
    assert prune([], Eq("continent", "europe")) == []


def test_prune_empty_generator_returns_empty():
    assert prune((p for p in []), Eq("year", 2024)) == []


# --------------------------------------------------------------------------
# count_pruned
# --------------------------------------------------------------------------

def test_count_pruned_returns_eliminated_count(partitions):
    # 4 total, Eq(year, 2024) keeps 2 -> 2 eliminated.
    assert count_pruned(partitions, Eq("year", 2024)) == 2


def test_count_pruned_none_eliminated(partitions):
    assert count_pruned(partitions, Always()) == 0


def test_count_pruned_all_eliminated(partitions):
    assert count_pruned(partitions, Eq("year", 1999)) == len(partitions)


def test_count_pruned_empty_input():
    assert count_pruned([], Eq("year", 2024)) == 0


def test_count_pruned_validates_predicate(partitions):
    # count_pruned delegates to prune (validate defaults to True), so an
    # unknown column surfaces as a PredicateError.
    with pytest.raises(PredicateError):
        count_pruned(partitions, Eq("continent", "europe"))


def test_count_pruned_consistent_with_prune(partitions):
    pred = In("region", ["us"])
    kept = prune(partitions, pred)
    assert count_pruned(partitions, pred) == len(partitions) - len(kept)


def test_count_pruned_accepts_generator(schema):
    rows = make_partitions(schema)
    assert count_pruned((p for p in rows), Eq("year", 2024)) == 2
