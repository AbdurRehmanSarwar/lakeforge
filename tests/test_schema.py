"""Tests for lakeforge.schema."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from lakeforge.errors import SchemaError
from lakeforge.schema import (
    ColumnType,
    PartitionColumn,
    PartitionSchema,
    schema,
)

# ---------------------------------------------------------------------------
# ColumnType.from_name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,expected",
    [
        ("string", ColumnType.STRING),
        ("int", ColumnType.INT),
        ("double", ColumnType.DOUBLE),
        ("boolean", ColumnType.BOOLEAN),
        ("date", ColumnType.DATE),
        ("timestamp", ColumnType.TIMESTAMP),
    ],
)
def test_from_name_canonical(name, expected):
    assert ColumnType.from_name(name) is expected


@pytest.mark.parametrize(
    "alias,expected",
    [
        ("str", ColumnType.STRING),
        ("integer", ColumnType.INT),
        ("bigint", ColumnType.INT),
        ("long", ColumnType.INT),
        ("float", ColumnType.DOUBLE),
        ("bool", ColumnType.BOOLEAN),
        ("ts", ColumnType.TIMESTAMP),
        ("datetime", ColumnType.TIMESTAMP),
    ],
)
def test_from_name_aliases(alias, expected):
    assert ColumnType.from_name(alias) is expected


@pytest.mark.parametrize(
    "name,expected",
    [
        ("INT", ColumnType.INT),
        ("BigInt", ColumnType.INT),
        ("  string  ", ColumnType.STRING),
        ("\tBOOL\n", ColumnType.BOOLEAN),
        ("Str", ColumnType.STRING),
    ],
)
def test_from_name_case_insensitive_and_stripped(name, expected):
    assert ColumnType.from_name(name) is expected


@pytest.mark.parametrize("bad", ["", "   ", "varchar", "number", "intt", "boolea"])
def test_from_name_unknown_raises(bad):
    with pytest.raises(SchemaError) as exc:
        ColumnType.from_name(bad)
    # message echoes the offending name and lists valid canonical types
    assert "unknown column type" in str(exc.value)


def test_from_name_error_lists_canonical_types():
    with pytest.raises(SchemaError) as exc:
        ColumnType.from_name("nope")
    msg = str(exc.value)
    for t in ColumnType:
        assert t.value in msg


# ---------------------------------------------------------------------------
# ColumnType.athena_type / PartitionColumn.athena_type
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ctype,athena",
    [
        (ColumnType.STRING, "string"),
        (ColumnType.INT, "bigint"),
        (ColumnType.DOUBLE, "double"),
        (ColumnType.BOOLEAN, "boolean"),
        (ColumnType.DATE, "date"),
        (ColumnType.TIMESTAMP, "timestamp"),
    ],
)
def test_athena_type_mapping(ctype, athena):
    assert ctype.athena_type == athena


def test_int_maps_to_bigint():
    assert ColumnType.INT.athena_type == "bigint"


def test_every_columntype_has_athena_mapping():
    for t in ColumnType:
        assert isinstance(t.athena_type, str) and t.athena_type


@pytest.mark.parametrize(
    "ctype,athena",
    [
        (ColumnType.STRING, "string"),
        (ColumnType.INT, "bigint"),
        (ColumnType.DOUBLE, "double"),
        (ColumnType.BOOLEAN, "boolean"),
        (ColumnType.DATE, "date"),
        (ColumnType.TIMESTAMP, "timestamp"),
    ],
)
def test_partition_column_athena_type_delegates(ctype, athena):
    assert PartitionColumn("c", ctype).athena_type == athena


# ---------------------------------------------------------------------------
# PartitionColumn construction / validation
# ---------------------------------------------------------------------------


def test_default_type_is_string():
    col = PartitionColumn("region")
    assert col.type is ColumnType.STRING


def test_empty_name_raises():
    with pytest.raises(SchemaError):
        PartitionColumn("")


def test_whitespace_name_raises():
    with pytest.raises(SchemaError):
        PartitionColumn("   ")


def test_type_string_is_coerced_to_columntype():
    # __post_init__ coerces a non-ColumnType type via from_name
    col = PartitionColumn("year", "bigint")
    assert col.type is ColumnType.INT


def test_type_bad_string_raises_on_construction():
    with pytest.raises(SchemaError):
        PartitionColumn("x", "varchar")


def test_partition_column_is_frozen():
    col = PartitionColumn("region")
    with pytest.raises(AttributeError):  # FrozenInstanceError subclasses AttributeError
        col.name = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PartitionColumn.parse for every type
# ---------------------------------------------------------------------------


def test_parse_string():
    col = PartitionColumn("region", ColumnType.STRING)
    assert col.parse("us-east-1") == "us-east-1"
    # strings are returned verbatim, no stripping
    assert col.parse("  spaced  ") == "  spaced  "


def test_parse_int():
    col = PartitionColumn("year", ColumnType.INT)
    assert col.parse("2024") == 2024
    assert col.parse("-5") == -5


@pytest.mark.parametrize("bad", ["abc", "1.5", "", "2024x", "0x10"])
def test_parse_int_bad_raises(bad):
    col = PartitionColumn("year", ColumnType.INT)
    with pytest.raises(SchemaError) as exc:
        col.parse(bad)
    assert "cannot parse" in str(exc.value)
    assert "year" in str(exc.value)


def test_parse_double():
    col = PartitionColumn("rate", ColumnType.DOUBLE)
    assert col.parse("1.5") == 1.5
    assert col.parse("3") == 3.0
    assert col.parse("-0.25") == -0.25


@pytest.mark.parametrize("bad", ["abc", "", "1.2.3", "one"])
def test_parse_double_bad_raises(bad):
    col = PartitionColumn("rate", ColumnType.DOUBLE)
    with pytest.raises(SchemaError):
        col.parse(bad)


@pytest.mark.parametrize(
    "raw", ["true", "t", "1", "yes", "y", "TRUE", "  True ", "Yes"]
)
def test_parse_boolean_true(raw):
    col = PartitionColumn("flag", ColumnType.BOOLEAN)
    assert col.parse(raw) is True


@pytest.mark.parametrize(
    "raw", ["false", "f", "0", "no", "n", "FALSE", "  No ", "N"]
)
def test_parse_boolean_false(raw):
    col = PartitionColumn("flag", ColumnType.BOOLEAN)
    assert col.parse(raw) is False


@pytest.mark.parametrize("bad", ["maybe", "", "2", "tru", "yesno"])
def test_parse_boolean_bad_raises(bad):
    col = PartitionColumn("flag", ColumnType.BOOLEAN)
    with pytest.raises(SchemaError) as exc:
        col.parse(bad)
    assert "boolean" in str(exc.value)


def test_parse_date():
    col = PartitionColumn("d", ColumnType.DATE)
    assert col.parse("2024-01-05") == date(2024, 1, 5)


@pytest.mark.parametrize("bad", ["2024/01/05", "not-a-date", "", "2024-13-01"])
def test_parse_date_bad_raises(bad):
    col = PartitionColumn("d", ColumnType.DATE)
    with pytest.raises(SchemaError):
        col.parse(bad)


def test_parse_timestamp():
    col = PartitionColumn("ts", ColumnType.TIMESTAMP)
    assert col.parse("2024-01-05T13:45:00") == datetime(2024, 1, 5, 13, 45, 0)
    # date-only is also accepted by datetime.fromisoformat
    assert col.parse("2024-01-05") == datetime(2024, 1, 5, 0, 0, 0)


@pytest.mark.parametrize("bad", ["not-a-ts", "", "2024-01-05 99:99"])
def test_parse_timestamp_bad_raises(bad):
    col = PartitionColumn("ts", ColumnType.TIMESTAMP)
    with pytest.raises(SchemaError):
        col.parse(bad)


# ---------------------------------------------------------------------------
# PartitionColumn.format for every type
# ---------------------------------------------------------------------------


def test_format_string():
    col = PartitionColumn("region", ColumnType.STRING)
    assert col.format("us-east-1") == "us-east-1"
    assert col.format(123) == "123"


def test_format_int():
    col = PartitionColumn("year", ColumnType.INT)
    assert col.format(2024) == "2024"
    assert col.format(-5) == "-5"


def test_format_double():
    col = PartitionColumn("rate", ColumnType.DOUBLE)
    assert col.format(1.5) == "1.5"
    assert col.format(3.0) == "3.0"


def test_format_boolean_from_bool():
    col = PartitionColumn("flag", ColumnType.BOOLEAN)
    assert col.format(True) == "true"
    assert col.format(False) == "false"


def test_format_boolean_uses_truthiness():
    # NOTE: format() for BOOLEAN keys off Python truthiness, not the boolean's
    # textual meaning. A non-empty string like "false" is truthy -> "true".
    col = PartitionColumn("flag", ColumnType.BOOLEAN)
    assert col.format("false") == "true"
    assert col.format("") == "false"
    assert col.format(0) == "false"
    assert col.format(1) == "true"


def test_format_date():
    col = PartitionColumn("d", ColumnType.DATE)
    assert col.format(date(2024, 1, 5)) == "2024-01-05"


def test_format_timestamp():
    col = PartitionColumn("ts", ColumnType.TIMESTAMP)
    assert col.format(datetime(2024, 1, 5, 13, 45, 0)) == "2024-01-05T13:45:00"


def test_format_date_value_on_string_column_uses_isoformat():
    # format() checks the value type (date/datetime) before falling back to str,
    # regardless of the declared column type.
    col = PartitionColumn("any", ColumnType.STRING)
    assert col.format(date(2024, 1, 5)) == "2024-01-05"


def test_parse_format_roundtrip():
    cases = [
        (ColumnType.STRING, "abc", "abc"),
        (ColumnType.INT, "2024", "2024"),
        (ColumnType.DOUBLE, "1.5", "1.5"),
        (ColumnType.DATE, "2024-01-05", "2024-01-05"),
        (ColumnType.TIMESTAMP, "2024-01-05T13:45:00", "2024-01-05T13:45:00"),
    ]
    for ctype, raw, expected in cases:
        col = PartitionColumn("c", ctype)
        assert col.format(col.parse(raw)) == expected


# ---------------------------------------------------------------------------
# PartitionSchema construction / validation
# ---------------------------------------------------------------------------


def test_schema_empty_raises():
    with pytest.raises(SchemaError) as exc:
        PartitionSchema(())
    assert "at least one column" in str(exc.value)


def test_schema_empty_default_raises():
    # default_factory yields an empty tuple, which must also raise
    with pytest.raises(SchemaError):
        PartitionSchema()


def test_schema_duplicate_columns_raises():
    with pytest.raises(SchemaError) as exc:
        PartitionSchema(
            (PartitionColumn("year", ColumnType.INT), PartitionColumn("year"))
        )
    assert "duplicate" in str(exc.value)


def test_schema_rejects_non_partition_column():
    with pytest.raises(SchemaError) as exc:
        PartitionSchema(("year",))  # type: ignore[arg-type]
    assert "PartitionColumn" in str(exc.value)


def test_schema_columns_coerced_to_tuple():
    cols = [PartitionColumn("year", ColumnType.INT), PartitionColumn("region")]
    sch = PartitionSchema(cols)
    assert isinstance(sch.columns, tuple)
    assert len(sch) == 2


def test_schema_names_and_iteration_order():
    sch = PartitionSchema(
        (
            PartitionColumn("year", ColumnType.INT),
            PartitionColumn("month", ColumnType.INT),
            PartitionColumn("region"),
        )
    )
    assert sch.names == ["year", "month", "region"]
    assert [c.name for c in sch] == ["year", "month", "region"]
    assert len(sch) == 3


# ---------------------------------------------------------------------------
# PartitionSchema.of
# ---------------------------------------------------------------------------


def test_of_with_strings():
    sch = PartitionSchema.of("region", "service")
    assert sch.names == ["region", "service"]
    assert all(c.type is ColumnType.STRING for c in sch)


def test_of_with_tuples_and_aliases():
    sch = PartitionSchema.of(("year", "int"), ("month", ColumnType.INT), "region")
    assert sch.names == ["year", "month", "region"]
    assert sch.column("year").type is ColumnType.INT
    assert sch.column("month").type is ColumnType.INT
    assert sch.column("region").type is ColumnType.STRING


def test_of_with_partition_column_instance():
    col = PartitionColumn("day", ColumnType.INT)
    sch = PartitionSchema.of(col)
    assert sch.columns == (col,)


def test_of_invalid_spec_raises():
    with pytest.raises(SchemaError) as exc:
        PartitionSchema.of(123)  # type: ignore[arg-type]
    assert "invalid column spec" in str(exc.value)


def test_of_wrong_tuple_length_raises():
    with pytest.raises(SchemaError):
        PartitionSchema.of(("year", "int", "extra"))  # type: ignore[arg-type]


def test_of_empty_raises():
    # no specs -> empty tuple -> empty-schema error
    with pytest.raises(SchemaError):
        PartitionSchema.of()


def test_of_bad_type_name_in_tuple_raises():
    with pytest.raises(SchemaError):
        PartitionSchema.of(("year", "varchar"))


def test_schema_alias_function_matches_of():
    sch = schema(("year", "int"), "region")
    assert sch.names == ["year", "region"]
    assert sch.column("year").type is ColumnType.INT


# ---------------------------------------------------------------------------
# PartitionSchema.parse
# ---------------------------------------------------------------------------


def test_parse_basic():
    sch = PartitionSchema.parse("year:int,month:int,region")
    assert sch.names == ["year", "month", "region"]
    assert sch.column("year").type is ColumnType.INT
    assert sch.column("month").type is ColumnType.INT
    assert sch.column("region").type is ColumnType.STRING


def test_parse_with_whitespace_and_blank_tokens():
    sch = PartitionSchema.parse(" year : int , , region , ")
    assert sch.names == ["year", "region"]
    assert sch.column("year").type is ColumnType.INT


def test_parse_single_untyped_column():
    sch = PartitionSchema.parse("region")
    assert sch.names == ["region"]
    assert sch.column("region").type is ColumnType.STRING


def test_parse_aliases():
    sch = PartitionSchema.parse("ts:datetime,n:bigint,f:float,b:bool")
    assert sch.column("ts").type is ColumnType.TIMESTAMP
    assert sch.column("n").type is ColumnType.INT
    assert sch.column("f").type is ColumnType.DOUBLE
    assert sch.column("b").type is ColumnType.BOOLEAN


def test_parse_empty_string_raises():
    with pytest.raises(SchemaError) as exc:
        PartitionSchema.parse("")
    assert "no columns found" in str(exc.value)


def test_parse_only_commas_raises():
    with pytest.raises(SchemaError):
        PartitionSchema.parse(",, ,")


def test_parse_bad_type_raises():
    with pytest.raises(SchemaError):
        PartitionSchema.parse("year:varchar")


def test_parse_duplicate_columns_raises():
    with pytest.raises(SchemaError) as exc:
        PartitionSchema.parse("year:int,year")
    assert "duplicate" in str(exc.value)


# ---------------------------------------------------------------------------
# PartitionSchema.column / has_column
# ---------------------------------------------------------------------------


def test_column_lookup():
    sch = PartitionSchema.parse("year:int,region")
    assert sch.column("year").type is ColumnType.INT


def test_column_lookup_missing_raises():
    sch = PartitionSchema.parse("year:int,region")
    with pytest.raises(SchemaError) as exc:
        sch.column("missing")
    assert "not in schema" in str(exc.value)


def test_has_column():
    sch = PartitionSchema.parse("year:int,region")
    assert sch.has_column("year") is True
    assert sch.has_column("region") is True
    assert sch.has_column("nope") is False


# ---------------------------------------------------------------------------
# PartitionSchema.coerce
# ---------------------------------------------------------------------------


def test_coerce_parses_string_values():
    sch = PartitionSchema.parse("year:int,month:int,region")
    out = sch.coerce({"year": "2024", "month": "01", "region": "us-east-1"})
    assert out == {"year": 2024, "month": 1, "region": "us-east-1"}


def test_coerce_passes_non_string_values_through():
    # coerce only parses str values; already-typed values pass through verbatim
    sch = PartitionSchema.parse("year:int,d:date")
    d = date(2024, 1, 5)
    out = sch.coerce({"year": 2024, "d": d})
    assert out == {"year": 2024, "d": d}


def test_coerce_missing_column_raises():
    sch = PartitionSchema.parse("year:int,month:int")
    with pytest.raises(SchemaError) as exc:
        sch.coerce({"year": "2024"})
    assert "missing values" in str(exc.value)
    assert "month" in str(exc.value)


def test_coerce_extra_column_raises():
    sch = PartitionSchema.parse("year:int")
    with pytest.raises(SchemaError) as exc:
        sch.coerce({"year": "2024", "bogus": "x"})
    assert "unexpected columns" in str(exc.value)
    assert "bogus" in str(exc.value)


def test_coerce_missing_takes_precedence_over_extra():
    # missing check runs before extra check
    sch = PartitionSchema.parse("year:int,month:int")
    with pytest.raises(SchemaError) as exc:
        sch.coerce({"year": "2024", "bogus": "x"})
    assert "missing values" in str(exc.value)


def test_coerce_bad_value_raises():
    sch = PartitionSchema.parse("year:int")
    with pytest.raises(SchemaError) as exc:
        sch.coerce({"year": "not-an-int"})
    assert "cannot parse" in str(exc.value)


def test_coerce_returns_new_dict():
    sch = PartitionSchema.parse("region")
    src = {"region": "us"}
    out = sch.coerce(src)
    assert out is not src
    assert out == {"region": "us"}
