"""Command-line interface for lakeforge.

Run ``lakeforge --help`` for usage. Subcommands cover the common one-off tasks:

* ``parse``        - parse an S3 key/path into typed partition values
* ``path``         - build a partition path from values
* ``add-partition``- emit ``ALTER TABLE ... ADD PARTITION`` DDL
* ``create-table`` - emit ``CREATE EXTERNAL TABLE`` DDL
* ``discover``     - list partitions present under an S3 prefix (needs boto3)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from . import __version__
from .errors import LakeForgeError
from .glue import add_partition_ddl, create_table_ddl
from .partition import Partition
from .schema import PartitionSchema


def _parse_assignments(pairs: Sequence[str]) -> dict[str, str]:
    """Turn ``["year=2024", "region=us"]`` into a dict, raising on bad input."""
    values: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise LakeForgeError(f"expected key=value, got {pair!r}")
        key, _, value = pair.partition("=")
        values[key.strip()] = value
    return values


def _cmd_parse(args: argparse.Namespace) -> int:
    schema = PartitionSchema.parse(args.schema)
    partition = Partition.parse(args.path, schema)
    print(json.dumps(partition.to_dict(), default=str, indent=2))
    return 0


def _cmd_path(args: argparse.Namespace) -> int:
    schema = PartitionSchema.parse(args.schema)
    partition = Partition(_parse_assignments(args.values), schema)
    print(partition.path(trailing_slash=args.trailing_slash))
    return 0


def _cmd_add_partition(args: argparse.Namespace) -> int:
    schema = PartitionSchema.parse(args.schema)
    partition = Partition(_parse_assignments(args.values), schema)
    print(
        add_partition_ddl(
            args.table,
            partition,
            args.location,
            database=args.database,
        )
    )
    return 0


def _cmd_create_table(args: argparse.Namespace) -> int:
    schema = PartitionSchema.parse(args.schema)
    columns = _parse_assignments(args.column) if args.column else {}
    print(
        create_table_ddl(
            args.table,
            columns,
            schema,
            args.location,
            database=args.database,
            stored_as=args.stored_as,
        )
    )
    return 0


def _cmd_discover(args: argparse.Namespace) -> int:
    from .discovery import discover_partitions

    schema = PartitionSchema.parse(args.schema)
    partitions = discover_partitions(args.bucket, args.prefix, schema, strict=args.strict)
    for partition in partitions:
        print(partition.path())
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct the argparse parser for the ``lakeforge`` command."""
    parser = argparse.ArgumentParser(
        prog="lakeforge",
        description="Tools for Hive-partitioned data lakes on S3.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_schema(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--schema",
            required=True,
            help='partition schema, e.g. "year:int,month:int,region"',
        )

    p_parse = sub.add_parser("parse", help="parse an S3 key/path into typed values")
    add_schema(p_parse)
    p_parse.add_argument("path", help="partition path or S3 key to parse")
    p_parse.set_defaults(func=_cmd_parse)

    p_path = sub.add_parser("path", help="build a partition path from values")
    add_schema(p_path)
    p_path.add_argument("values", nargs="+", metavar="COL=VALUE")
    p_path.add_argument("--trailing-slash", action="store_true")
    p_path.set_defaults(func=_cmd_path)

    p_add = sub.add_parser("add-partition", help="emit ALTER TABLE ... ADD PARTITION DDL")
    add_schema(p_add)
    p_add.add_argument("--table", required=True)
    p_add.add_argument("--database")
    p_add.add_argument("--location", required=True, help="base S3 location for the table")
    p_add.add_argument("values", nargs="+", metavar="COL=VALUE")
    p_add.set_defaults(func=_cmd_add_partition)

    p_create = sub.add_parser("create-table", help="emit CREATE EXTERNAL TABLE DDL")
    add_schema(p_create)
    p_create.add_argument("--table", required=True)
    p_create.add_argument("--database")
    p_create.add_argument("--location", required=True)
    p_create.add_argument("--stored-as", default="PARQUET")
    p_create.add_argument(
        "--column",
        action="append",
        metavar="NAME=TYPE",
        help="a non-partition column, e.g. --column event_id=string (repeatable)",
    )
    p_create.set_defaults(func=_cmd_create_table)

    p_discover = sub.add_parser("discover", help="list partitions under an S3 prefix")
    add_schema(p_discover)
    p_discover.add_argument("--bucket", required=True)
    p_discover.add_argument("--prefix", default="")
    p_discover.add_argument("--strict", action="store_true")
    p_discover.set_defaults(func=_cmd_discover)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except LakeForgeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
