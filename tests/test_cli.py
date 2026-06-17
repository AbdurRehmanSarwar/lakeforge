"""Tests for the lakeforge.cli module.

These drive ``lakeforge.cli.main(argv=[...])`` directly and capture stdout/stderr
with pytest's ``capsys`` fixture. The ``discover`` subcommand is exercised both
against a moto-backed S3 bucket (the real boto3 path) and via monkeypatching.
"""

from __future__ import annotations

import json

import pytest

from lakeforge import cli

# ---------------------------------------------------------------------------
# parse
# ---------------------------------------------------------------------------

def test_parse_typed_values(capsys):
    rc = cli.main(
        [
            "parse",
            "--schema",
            "year:int,month:int,region",
            "logs/year=2024/month=1/region=us/file.parquet",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data == {"year": 2024, "month": 1, "region": "us"}


def test_parse_bare_path(capsys):
    rc = cli.main(["parse", "--schema", "year:int,region", "year=2024/region=eu"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data == {"year": 2024, "region": "eu"}


def test_parse_missing_column_returns_error(capsys):
    # The path lacks the 'region' column, so Partition.parse raises a
    # PartitionParseError (a LakeForgeError), which main() turns into rc 1.
    rc = cli.main(["parse", "--schema", "year:int,region", "year=2024"])
    assert rc == 1
    captured = capsys.readouterr()
    assert captured.err.startswith("error: ")
    assert "region" in captured.err


# ---------------------------------------------------------------------------
# path
# ---------------------------------------------------------------------------

def test_path_basic(capsys):
    rc = cli.main(
        ["path", "--schema", "year:int,month:int,region", "year=2024", "month=1", "region=us"]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert out == "year=2024/month=1/region=us\n"


def test_path_trailing_slash(capsys):
    rc = cli.main(
        [
            "path",
            "--schema",
            "year:int,month:int,region",
            "year=2024",
            "month=1",
            "region=us",
            "--trailing-slash",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert out == "year=2024/month=1/region=us/\n"


def test_path_bad_assignment_returns_error(capsys):
    rc = cli.main(["path", "--schema", "year:int", "year2024"])
    assert rc == 1
    captured = capsys.readouterr()
    assert captured.err == "error: expected key=value, got 'year2024'\n"
    assert captured.out == ""


# ---------------------------------------------------------------------------
# add-partition
# ---------------------------------------------------------------------------

def test_add_partition_basic(capsys):
    rc = cli.main(
        [
            "add-partition",
            "--schema",
            "year:int,region",
            "--table",
            "events",
            "--location",
            "s3://bucket/events",
            "year=2024",
            "region=us",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert out == (
        "ALTER TABLE events ADD IF NOT EXISTS PARTITION (year=2024, region='us') "
        "LOCATION 's3://bucket/events/year=2024/region=us/';\n"
    )


def test_add_partition_with_database(capsys):
    rc = cli.main(
        [
            "add-partition",
            "--schema",
            "year:int,region",
            "--table",
            "events",
            "--database",
            "analytics",
            "--location",
            "s3://bucket/events",
            "year=2024",
            "region=us",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert out.startswith("ALTER TABLE analytics.events ADD IF NOT EXISTS PARTITION")


def test_add_partition_bad_assignment_returns_error(capsys):
    rc = cli.main(
        [
            "add-partition",
            "--schema",
            "year:int",
            "--table",
            "events",
            "--location",
            "s3://bucket/events",
            "nope",
        ]
    )
    assert rc == 1
    captured = capsys.readouterr()
    assert captured.err == "error: expected key=value, got 'nope'\n"


# ---------------------------------------------------------------------------
# create-table
# ---------------------------------------------------------------------------

def test_create_table_repeated_column(capsys):
    rc = cli.main(
        [
            "create-table",
            "--schema",
            "year:int,region",
            "--table",
            "events",
            "--location",
            "s3://bucket/events",
            "--column",
            "event_id=string",
            "--column",
            "amount=double",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert out == (
        "CREATE EXTERNAL TABLE IF NOT EXISTS events (\n"
        "  event_id string,\n"
        "  amount double\n"
        ") PARTITIONED BY (year bigint, region string)\n"
        "STORED AS PARQUET\n"
        "LOCATION 's3://bucket/events/';\n"
    )


def test_create_table_custom_stored_as(capsys):
    rc = cli.main(
        [
            "create-table",
            "--schema",
            "year:int",
            "--table",
            "events",
            "--location",
            "s3://bucket/events",
            "--stored-as",
            "ORC",
            "--column",
            "event_id=string",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "STORED AS ORC\n" in out


def test_create_table_no_columns(capsys):
    # --column is optional; with none, create_table_ddl gets an empty mapping.
    rc = cli.main(
        [
            "create-table",
            "--schema",
            "year:int",
            "--table",
            "events",
            "--location",
            "s3://bucket/events",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert out.startswith("CREATE EXTERNAL TABLE IF NOT EXISTS events (\n")
    assert "PARTITIONED BY (year bigint)" in out


def test_create_table_bad_column_returns_error(capsys):
    rc = cli.main(
        [
            "create-table",
            "--schema",
            "year:int",
            "--table",
            "events",
            "--location",
            "s3://bucket/events",
            "--column",
            "bogus",
        ]
    )
    assert rc == 1
    captured = capsys.readouterr()
    assert captured.err == "error: expected key=value, got 'bogus'\n"


# ---------------------------------------------------------------------------
# discover (moto-backed real boto3 path)
# ---------------------------------------------------------------------------

@pytest.fixture
def aws_credentials(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


def test_discover_with_moto(capsys, aws_credentials):
    moto = pytest.importorskip("moto")
    import boto3

    with moto.mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="mybucket")
        s3.put_object(Bucket="mybucket", Key="data/year=2024/region=eu/a.parquet", Body=b"x")
        s3.put_object(Bucket="mybucket", Key="data/year=2024/region=us/b.parquet", Body=b"x")
        s3.put_object(Bucket="mybucket", Key="data/year=2024/region=us/c.parquet", Body=b"x")
        # A key without a full partition path is silently skipped (non-strict).
        s3.put_object(Bucket="mybucket", Key="data/_garbage.txt", Body=b"x")

        rc = cli.main(
            [
                "discover",
                "--schema",
                "year:int,region",
                "--bucket",
                "mybucket",
                "--prefix",
                "data/",
            ]
        )

    assert rc == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    # De-duplicated, first-seen order. moto lists keys lexicographically so
    # 'eu' is seen before 'us'.
    assert lines == ["year=2024/region=eu", "year=2024/region=us"]


def test_discover_strict_raises_on_bad_key(capsys, aws_credentials):
    moto = pytest.importorskip("moto")
    import boto3


    with moto.mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="strictbucket")
        s3.put_object(Bucket="strictbucket", Key="data/not-a-partition.txt", Body=b"x")

        # In --strict mode a key that isn't a full partition path raises
        # PartitionParseError, which propagates out of main() (it is caught as a
        # LakeForgeError subclass -> rc 1). Confirm current behavior: rc 1.
        rc = cli.main(
            [
                "discover",
                "--schema",
                "year:int,region",
                "--bucket",
                "strictbucket",
                "--prefix",
                "data/",
                "--strict",
            ]
        )

    assert rc == 1
    assert capsys.readouterr().err.startswith("error: ")


def test_discover_monkeypatched(capsys, monkeypatch):
    from lakeforge.partition import Partition

    captured_args = {}

    def fake_discover(bucket, prefix, schema, *, strict=False):
        captured_args["bucket"] = bucket
        captured_args["prefix"] = prefix
        captured_args["strict"] = strict
        captured_args["schema_names"] = schema.names
        return [
            Partition({"year": 2024, "region": "us"}, schema),
            Partition({"year": 2025, "region": "eu"}, schema),
        ]

    # cli imports discover_partitions inside the function from .discovery, so
    # patch it at its definition module.
    monkeypatch.setattr("lakeforge.discovery.discover_partitions", fake_discover)

    rc = cli.main(
        [
            "discover",
            "--schema",
            "year:int,region",
            "--bucket",
            "thebucket",
            "--prefix",
            "events/",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert out == "year=2024/region=us\nyear=2025/region=eu\n"
    assert captured_args == {
        "bucket": "thebucket",
        "prefix": "events/",
        "strict": False,
        "schema_names": ["year", "region"],
    }


def test_discover_prefix_defaults_empty(capsys, monkeypatch):
    seen = {}

    def fake_discover(bucket, prefix, schema, *, strict=False):
        seen["prefix"] = prefix
        seen["strict"] = strict
        return []

    monkeypatch.setattr("lakeforge.discovery.discover_partitions", fake_discover)
    rc = cli.main(["discover", "--schema", "year:int", "--bucket", "b"])
    assert rc == 0
    assert capsys.readouterr().out == ""
    assert seen == {"prefix": "", "strict": False}


# ---------------------------------------------------------------------------
# --version and argparse-level behavior
# ---------------------------------------------------------------------------

def test_version_exits_zero(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--version"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert out.startswith("lakeforge ")


def test_no_command_required(capsys):
    # The subparsers group is required=True, so argparse exits with code 2.
    with pytest.raises(SystemExit) as excinfo:
        cli.main([])
    assert excinfo.value.code == 2


def test_unknown_command_exits_two(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["nonsense"])
    assert excinfo.value.code == 2


def test_missing_required_schema_exits_two(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["parse", "somepath"])
    assert excinfo.value.code == 2


def test_build_parser_returns_parser():
    import argparse

    parser = cli.build_parser()
    assert isinstance(parser, argparse.ArgumentParser)
    assert parser.prog == "lakeforge"
