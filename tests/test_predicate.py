"""Tests for lakeforge.predicate."""

from __future__ import annotations

import pytest

from lakeforge.predicate import (
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

# ---------------------------------------------------------------------------
# Comparison predicates: evaluate
# ---------------------------------------------------------------------------


def test_eq_evaluate():
    p = Eq("year", 2023)
    assert p.evaluate({"year": 2023}) is True
    assert p.evaluate({"year": 2024}) is False


def test_ne_evaluate():
    p = Ne("year", 2023)
    assert p.evaluate({"year": 2024}) is True
    assert p.evaluate({"year": 2023}) is False


def test_gt_evaluate():
    p = Gt("year", 2023)
    assert p.evaluate({"year": 2024}) is True
    assert p.evaluate({"year": 2023}) is False
    assert p.evaluate({"year": 2022}) is False


def test_ge_evaluate():
    p = Ge("year", 2023)
    assert p.evaluate({"year": 2024}) is True
    assert p.evaluate({"year": 2023}) is True
    assert p.evaluate({"year": 2022}) is False


def test_lt_evaluate():
    p = Lt("year", 2023)
    assert p.evaluate({"year": 2022}) is True
    assert p.evaluate({"year": 2023}) is False
    assert p.evaluate({"year": 2024}) is False


def test_le_evaluate():
    p = Le("year", 2023)
    assert p.evaluate({"year": 2022}) is True
    assert p.evaluate({"year": 2023}) is True
    assert p.evaluate({"year": 2024}) is False


def test_in_evaluate():
    p = In("region", ["us", "eu"])
    assert p.evaluate({"region": "us"}) is True
    assert p.evaluate({"region": "eu"}) is True
    assert p.evaluate({"region": "apac"}) is False


def test_in_normalizes_to_tuple():
    p = In("region", ["us", "eu"])
    assert p.values == ("us", "eu")
    assert isinstance(p.values, tuple)


def test_in_accepts_arbitrary_iterable():
    p = In("region", (r for r in ["us", "eu"]))
    assert p.values == ("us", "eu")
    assert p.evaluate({"region": "eu"}) is True
    assert p.evaluate({"region": "apac"}) is False


def test_in_empty_values():
    p = In("region", [])
    assert p.values == ()
    assert p.evaluate({"region": "us"}) is False


def test_between_evaluate_inclusive():
    p = Between("year", 2020, 2023)
    assert p.evaluate({"year": 2020}) is True  # inclusive low
    assert p.evaluate({"year": 2023}) is True  # inclusive high
    assert p.evaluate({"year": 2021}) is True
    assert p.evaluate({"year": 2019}) is False
    assert p.evaluate({"year": 2024}) is False


def test_comparison_evaluate_missing_column_raises_keyerror():
    p = Eq("year", 2023)
    with pytest.raises(KeyError):
        p.evaluate({"region": "us"})


# ---------------------------------------------------------------------------
# columns()
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "pred",
    [
        Eq("year", 2023),
        Ne("year", 2023),
        Gt("year", 2023),
        Ge("year", 2023),
        Lt("year", 2023),
        Le("year", 2023),
        In("year", [2023]),
        Between("year", 2020, 2023),
    ],
)
def test_single_column_predicate_columns(pred):
    assert pred.columns() == {"year"}


def test_and_columns_union():
    p = And(Eq("year", 2023), In("region", ["us"]), Gt("day", 1))
    assert p.columns() == {"year", "region", "day"}


def test_or_columns_union():
    p = Or(Eq("year", 2023), In("region", ["us"]))
    assert p.columns() == {"year", "region"}


def test_empty_and_columns():
    assert And().columns() == set()


def test_empty_or_columns():
    assert Or().columns() == set()


def test_not_columns_delegates_to_inner():
    p = Not(Eq("year", 2023))
    assert p.columns() == {"year"}


def test_nested_columns():
    p = And(Eq("year", 2023), Or(Eq("region", "us"), Not(Eq("day", 1))))
    assert p.columns() == {"year", "region", "day"}


def test_always_columns_empty():
    assert Always().columns() == set()


# ---------------------------------------------------------------------------
# And / Or / Not evaluate
# ---------------------------------------------------------------------------


def test_and_all_true():
    p = And(Eq("year", 2023), Eq("region", "us"))
    assert p.evaluate({"year": 2023, "region": "us"}) is True


def test_and_one_false():
    p = And(Eq("year", 2023), Eq("region", "us"))
    assert p.evaluate({"year": 2023, "region": "eu"}) is False


def test_and_short_circuits():
    # The second part references a missing column; because the first part is
    # False and ``all`` short-circuits, evaluate must not raise.
    p = And(Eq("year", 2024), Eq("region", "us"))
    assert p.evaluate({"year": 2023}) is False


def test_or_one_true():
    p = Or(Eq("year", 2023), Eq("region", "us"))
    assert p.evaluate({"year": 2023, "region": "eu"}) is True


def test_or_all_false():
    p = Or(Eq("year", 2023), Eq("region", "us"))
    assert p.evaluate({"year": 2024, "region": "eu"}) is False


def test_or_short_circuits():
    # First part is True, so ``any`` should short-circuit before the second
    # (missing-column) part is evaluated.
    p = Or(Eq("year", 2023), Eq("region", "us"))
    assert p.evaluate({"year": 2023}) is True


def test_not_evaluate():
    p = Not(Eq("year", 2023))
    assert p.evaluate({"year": 2024}) is True
    assert p.evaluate({"year": 2023}) is False


def test_double_not():
    p = Not(Not(Eq("year", 2023)))
    assert p.evaluate({"year": 2023}) is True
    assert p.evaluate({"year": 2024}) is False


# ---------------------------------------------------------------------------
# Empty And / Or identities
# ---------------------------------------------------------------------------


def test_empty_and_is_true():
    assert And().evaluate({}) is True
    assert And().evaluate({"year": 2023}) is True


def test_empty_or_is_false():
    assert Or().evaluate({}) is False
    assert Or().evaluate({"year": 2023}) is False


# ---------------------------------------------------------------------------
# Always
# ---------------------------------------------------------------------------


def test_always_matches_everything():
    p = Always()
    assert p.evaluate({}) is True
    assert p.evaluate({"year": 2023}) is True
    assert p.evaluate({"anything": object()}) is True


# ---------------------------------------------------------------------------
# Operators &, |, ~
# ---------------------------------------------------------------------------


def test_and_operator_builds_and():
    a, b = Eq("year", 2023), Eq("region", "us")
    p = a & b
    assert isinstance(p, And)
    assert p.parts == (a, b)


def test_or_operator_builds_or():
    a, b = Eq("year", 2023), Eq("region", "us")
    p = a | b
    assert isinstance(p, Or)
    assert p.parts == (a, b)


def test_invert_operator_builds_not():
    a = Eq("year", 2023)
    p = ~a
    assert isinstance(p, Not)
    assert p.inner is a


def test_operator_combination_evaluates():
    p = (Eq("year", 2023) & In("region", ["us", "eu"])) | Eq("special", True)
    assert isinstance(p, Or)
    assert p.evaluate({"year": 2023, "region": "us", "special": False}) is True
    assert p.evaluate({"year": 2022, "region": "us", "special": False}) is False
    assert p.evaluate({"year": 2022, "region": "us", "special": True}) is True


def test_and_operator_does_not_flatten():
    # ``&`` always wraps in a new binary And rather than flattening.
    a, b, c = Eq("a", 1), Eq("b", 2), Eq("c", 3)
    p = a & b & c
    assert isinstance(p, And)
    assert len(p.parts) == 2
    assert isinstance(p.parts[0], And)
    assert p.parts[1] is c


# ---------------------------------------------------------------------------
# field() fluent DSL
# ---------------------------------------------------------------------------


def test_field_returns_partition_field():
    f = field("year")
    assert isinstance(f, PartitionField)
    assert f.name == "year"


def test_field_eq_builds_eq():
    p = field("year") == 2023
    assert isinstance(p, Eq)
    assert p == Eq("year", 2023)
    assert p.column == "year"
    assert p.value == 2023


def test_field_ne_builds_ne():
    p = field("year") != 2023
    assert isinstance(p, Ne)
    assert p == Ne("year", 2023)


def test_field_gt_builds_gt():
    p = field("year") > 2023
    assert isinstance(p, Gt)
    assert p == Gt("year", 2023)


def test_field_ge_builds_ge():
    p = field("year") >= 2023
    assert isinstance(p, Ge)
    assert p == Ge("year", 2023)


def test_field_lt_builds_lt():
    p = field("year") < 2023
    assert isinstance(p, Lt)
    assert p == Lt("year", 2023)


def test_field_le_builds_le():
    p = field("year") <= 2023
    assert isinstance(p, Le)
    assert p == Le("year", 2023)


def test_field_isin_builds_in():
    p = field("region").isin(["us", "eu"])
    assert isinstance(p, In)
    assert p == In("region", ["us", "eu"])
    assert p.values == ("us", "eu")


def test_field_between_builds_between():
    p = field("year").between(2020, 2023)
    assert isinstance(p, Between)
    assert p == Between("year", 2020, 2023)


def test_field_dsl_full_expression_matches_explicit():
    dsl = (field("year") >= 2023) & field("region").isin(["us", "eu"])
    explicit = And(Ge("year", 2023), In("region", ("us", "eu")))
    assert dsl == explicit
    assert dsl.evaluate({"year": 2023, "region": "us"}) is True
    assert dsl.evaluate({"year": 2023, "region": "apac"}) is False
    assert dsl.evaluate({"year": 2022, "region": "us"}) is False


def test_field_is_unhashable():
    # PartitionField sets __hash__ = None so it cannot be used as a dict key.
    with pytest.raises(TypeError):
        hash(field("year"))


# ---------------------------------------------------------------------------
# dataclass equality / hashing of predicates
# ---------------------------------------------------------------------------


def test_comparison_equality_and_hash():
    assert Eq("a", 1) == Eq("a", 1)
    assert hash(Eq("a", 1)) == hash(Eq("a", 1))
    assert Eq("a", 1) != Eq("a", 2)
    assert Eq("a", 1) != Eq("b", 1)


def test_distinct_comparison_subclasses_not_equal():
    # Same column/value but different subclass should not compare equal.
    assert Eq("a", 1) != Ne("a", 1)
    assert Gt("a", 1) != Ge("a", 1)


def test_in_equality_and_hash():
    assert In("a", [1, 2]) == In("a", [1, 2])
    assert hash(In("a", [1, 2])) == hash(In("a", [1, 2]))
    assert In("a", [1, 2]) != In("a", [2, 1])


def test_between_equality():
    assert Between("a", 1, 2) == Between("a", 1, 2)
    assert Between("a", 1, 2) != Between("a", 1, 3)


def test_and_or_equality():
    assert And(Eq("a", 1)) == And(Eq("a", 1))
    assert Or(Eq("a", 1)) == Or(Eq("a", 1))
    assert And(Eq("a", 1)) != Or(Eq("a", 1))


def test_always_equality():
    assert Always() == Always()


# ---------------------------------------------------------------------------
# ABC contract
# ---------------------------------------------------------------------------


def test_predicate_is_abstract():
    with pytest.raises(TypeError):
        Predicate()  # type: ignore[abstract]


def test_predicates_are_predicate_instances():
    for p in [
        Eq("a", 1),
        In("a", [1]),
        Between("a", 1, 2),
        And(),
        Or(),
        Not(Eq("a", 1)),
        Always(),
    ]:
        assert isinstance(p, Predicate)
