# lakeforge

**A typed toolkit for Hive-partitioned data lakes on S3 — partition paths, predicate pruning, Athena/Glue DDL, manifests, and S3 discovery.**

[![CI](https://github.com/AbdurRehmanSarwar/lakeforge/actions/workflows/ci.yml/badge.svg)](https://github.com/AbdurRehmanSarwar/lakeforge/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/AbdurRehmanSarwar/lakeforge/blob/main/LICENSE)
[![Python 3.9–3.12](https://img.shields.io/badge/python-3.9%20%7C%203.10%20%7C%203.11%20%7C%203.12-blue.svg)](https://github.com/AbdurRehmanSarwar/lakeforge)

---

## Why lakeforge

If you run a data lake on Amazon S3 with Athena, AWS Glue, or Redshift Spectrum,
you spend a surprising amount of time wrangling Hive-style partition layouts:

- **Partition paths are stringly-typed.** A key like
  `year=2024/month=3/region=us/part-0.parquet` is just text. Building it,
  parsing it back, and keeping `year`/`month` as integers (and dates as real
  dates) is fiddly and error-prone when done by hand.
- **Pruning is reinvented everywhere.** Deciding which partitions a query
  actually needs — and proving you skipped the rest — usually means ad-hoc
  comparisons scattered across scripts.
- **DDL is copy-pasted SQL.** `CREATE EXTERNAL TABLE`,
  `ALTER TABLE ... ADD PARTITION`, `MSCK REPAIR TABLE`, and Athena
  *partition projection* properties are tedious and easy to get subtly wrong
  (quoting, `bigint` vs `int`, trailing slashes).
- **Discovery and manifests are bespoke.** Listing the partitions that physically
  exist under a prefix, and tracking which files belong to which partition,
  tends to be one-off boto3 glue code.

`lakeforge` turns each of these into a small, typed, well-tested primitive:

- A **`PartitionSchema`** of typed columns that knows how to parse, format, and
  map to Athena types.
- **`Partition`** objects that render Hive paths / S3 URIs and parse cleanly back
  out of any key.
- A composable **predicate** language (`&`, `|`, `~`, plus a fluent DSL) and a
  `prune` function that filters partitions and reports selectivity.
- Pure-string **Athena/Glue DDL** builders, including partition projection.
- **Manifests** that serialize to lakeforge JSON or to the Redshift
  Spectrum / Athena file-manifest format.
- Optional **S3 discovery** (via `boto3`) to reconstruct partitions and
  manifests from objects that already exist.

The core library has **zero runtime dependencies** — `boto3` is only needed for
the optional S3 discovery feature.

## Installation

```bash
pip install lakeforge
```

The core package (schemas, partitions, predicates, pruning, DDL, manifests, CLI)
has no third-party dependencies. To enable S3 discovery, install the `aws`
extra, which pulls in `boto3`:

```bash
pip install "lakeforge[aws]"
```

Requires Python 3.9 or newer.

## Quickstart

```python
from lakeforge import PartitionSchema, Partition, field, prune

# Define a typed partition layout.
sch = PartitionSchema.parse("year:int,month:int,region")

# Build a partition and render Hive-style paths / S3 URIs.
p = Partition.of(sch, year=2024, month=3, region="us")
p.path()                       # 'year=2024/month=3/region=us'
p.s3_uri("s3://my-bucket/events")
# 's3://my-bucket/events/year=2024/month=3/region=us/'

# Prune a set of partitions with a predicate.
partitions = [
    Partition.of(sch, year=2024, month=m, region=r)
    for m in (1, 2, 3)
    for r in ("us", "eu")
]
kept = prune(partitions, (field("month") >= 2) & field("region").isin(["us"]))
[part.path() for part in kept]
# ['year=2024/month=2/region=us', 'year=2024/month=3/region=us']
```

## Schemas

A `PartitionSchema` is an ordered collection of typed `PartitionColumn`s. Column
order is significant — it defines the order of segments in a Hive path. Supported
types are `string`, `int`, `double`, `boolean`, `date`, and `timestamp`
(`ColumnType`), with common aliases such as `str`, `integer`, `bigint`, `float`,
`bool`, and `ts` accepted when parsing.

```python
from datetime import date
from lakeforge import ColumnType, PartitionColumn, PartitionSchema, schema

# Three equivalent ways to build a schema.
s1 = PartitionSchema.of(("year", "int"), ("month", "int"), "region")
s2 = PartitionSchema.parse("year:int,month:int,region")
s3 = schema(
    PartitionColumn("year", ColumnType.INT),
    PartitionColumn("month", ColumnType.INT),
    PartitionColumn("region"),  # defaults to STRING
)
assert s1 == s2 == s3

s1.names                       # ['year', 'month', 'region']
s1.column("year").athena_type  # 'bigint'  (INT maps to Athena bigint)

# Columns parse raw path segments into typed Python values and back.
day = PartitionColumn("day", ColumnType.DATE)
day.parse("2024-03-05")        # datetime.date(2024, 3, 5)
day.format(date(2024, 3, 5))   # '2024-03-05'

# Coerce a dict of raw strings into typed values (validates missing/extra keys).
s1.coerce({"year": "2024", "month": "3", "region": "us"})
# {'year': 2024, 'month': 3, 'region': 'us'}
```

> **Tip:** integer columns render without zero-padding (`month=3`). If you need
> zero-padded segments like `month=03`, declare the column as a `string` and pass
> the literal `"03"`.

## Partitions & paths

A `Partition` binds typed column values to a schema. It renders Hive paths and
full S3 URIs, and parses back out of any key — leading prefixes and trailing
filenames are ignored. Segment values are percent-encoded so arbitrary strings
round-trip safely.

```python
from lakeforge import Partition, PartitionSchema, build_partitions

sch = PartitionSchema.parse("year:int,month:int,region")

p = Partition.of(sch, year=2024, month=3, region="us")
p.path()                            # 'year=2024/month=3/region=us'
p.path(trailing_slash=True)         # 'year=2024/month=3/region=us/'
p.s3_uri("s3://bucket/events")      # 's3://bucket/events/year=2024/month=3/region=us/'

# Parse a partition back out of a full S3 key.
key = "s3://bucket/events/year=2024/month=3/region=us/part-0000.parquet"
back = Partition.parse(key, sch)
back.to_dict()                      # {'year': 2024, 'month': 3, 'region': 'us'}
back["year"], back.values["region"] # (2024, 'us')

# Build many partitions at once from rows of values.
rows = [
    {"year": 2024, "month": 1, "region": "us"},
    {"year": 2024, "month": 2, "region": "eu"},
]
[part.path() for part in build_partitions(sch, rows)]
# ['year=2024/month=1/region=us', 'year=2024/month=2/region=eu']
```

## Predicates & pruning

Predicates describe a filter over partition values. Use the explicit classes
(`Eq`, `Ne`, `Gt`, `Ge`, `Lt`, `Le`, `In`, `Between`, `And`, `Or`, `Not`,
`Always`) or the fluent `field(...)` DSL, then combine them with `&`, `|`, and
`~`. `prune` returns the partitions that match; `count_pruned` reports how many
were eliminated.

```python
from lakeforge import (
    PartitionSchema, Partition,
    And, In, Between, field,
    prune, count_pruned, validate_predicate, PredicateError,
)

sch = PartitionSchema.parse("year:int,month:int,region")
partitions = [
    Partition.of(sch, year=y, month=m, region=r)
    for y in (2023, 2024)
    for m in range(1, 13)
    for r in ("us", "eu")
]

# Explicit predicate objects ...
pred = And(field("year") >= 2024, In("region", ["us"]), Between("month", 3, 6))

# ... or the fluent DSL, combined with & | ~.
pred = (
    (field("year") >= 2024)
    & field("region").isin(["us"])
    & field("month").between(3, 6)
)

kept = prune(partitions, pred)
len(partitions), len(kept)          # (48, 4)
count_pruned(partitions, pred)      # 44

# prune() validates predicate columns against the schema by default, so typos
# surface as a clear error instead of silently matching nothing.
try:
    validate_predicate(field("regon") == "us", sch)
except PredicateError as exc:
    print(exc)
# predicate references columns ['regon'] not in schema ['year', 'month', 'region']
```

## Athena / Glue DDL + partition projection

The `lakeforge.glue` module contains pure string builders — they never touch
AWS. Feed the resulting SQL to Athena via `boto3` (`StartQueryExecution`) or any
SQL client.

```python
from lakeforge import PartitionSchema, Partition
from lakeforge.glue import (
    create_table_ddl,
    add_partition_ddl,
    add_partitions_ddl,
    drop_partition_ddl,
    msck_repair,
    projection_properties,
)

sch = PartitionSchema.parse("year:int,month:int,region")

# CREATE EXTERNAL TABLE — non-partition columns map name -> Athena type;
# partition columns are emitted in PARTITIONED BY automatically.
print(create_table_ddl(
    "events",
    {"event_id": "string", "payload": "string"},
    sch,
    "s3://my-bucket/events/",
    database="analytics",
    stored_as="PARQUET",
))
```

```sql
CREATE EXTERNAL TABLE IF NOT EXISTS analytics.events (
  event_id string,
  payload string
) PARTITIONED BY (year bigint, month bigint, region string)
STORED AS PARQUET
LOCATION 's3://my-bucket/events/';
```

```python
p = Partition.of(sch, year=2024, month=3, region="us")
add_partition_ddl("events", p, "s3://my-bucket/events", database="analytics")
# ALTER TABLE analytics.events ADD IF NOT EXISTS PARTITION
#   (year=2024, month=3, region='us')
#   LOCATION 's3://my-bucket/events/year=2024/month=3/region=us/';

# Add many partitions in one statement (much faster than one call each).
ps = [Partition.of(sch, year=2024, month=m, region="us") for m in (1, 2, 3)]
add_partitions_ddl("events", ps, "s3://my-bucket/events")

# Let Athena re-discover existing partitions from the catalog.
msck_repair("events", database="analytics")
# 'MSCK REPAIR TABLE analytics.events;'

# Retire a partition (pair with add_partition_ddl to re-point its location).
drop_partition_ddl("events", p, database="analytics")
# "ALTER TABLE analytics.events DROP IF EXISTS PARTITION (year=2024, month=3, region='us');"
```

For large, regular layouts, **partition projection** lets Athena compute
partition locations from the query instead of listing them in the catalog. Build
the table properties with `projection_properties` and pass them straight into
`create_table_ddl`:

```python
props = projection_properties(
    sch,
    location_template=(
        "s3://my-bucket/events/year=${year}/month=${month}/region=${region}/"
    ),
    ranges={"year": (2020, 2030), "month": (1, 12)},
    digits={"month": 2},
    enum_values={"region": ["us", "eu", "apac"]},
)
print(create_table_ddl(
    "events",
    {"event_id": "string"},
    sch,
    "s3://my-bucket/events/",
    table_properties=props,
))
```

```sql
CREATE EXTERNAL TABLE IF NOT EXISTS events (
  event_id string
) PARTITIONED BY (year bigint, month bigint, region string)
STORED AS PARQUET
LOCATION 's3://my-bucket/events/'
TBLPROPERTIES ('projection.enabled'='true', 'storage.location.template'='s3://my-bucket/events/year=${year}/month=${month}/region=${region}/', 'projection.year.type'='integer', 'projection.year.range'='2020,2030', 'projection.month.type'='integer', 'projection.month.range'='1,12', 'projection.month.digits'='2', 'projection.region.type'='enum', 'projection.region.values'='us,eu,apac');
```

Integer columns project as `type=integer` over the given `ranges`, date/timestamp
columns as `type=date`, and string columns as `type=enum` from `enum_values`.

## Generating partitions (backfills)

When you backfill a date-partitioned table or register many partitions at once,
`lakeforge.generate` enumerates the partitions for you. `date_range` produces the
dates; `partition_grid` builds the cartesian product of partitions from per-column
value lists.

```python
from datetime import date
from lakeforge import schema, date_range, partition_grid
from lakeforge.glue import add_partitions_ddl

sch = schema(("year", "int"), ("month", "int"), "region")

# Every month-start from Jan 2024 through Mar 2024.
months = date_range(date(2024, 1, 1), date(2024, 3, 1), step="month")
# [date(2024, 1, 1), date(2024, 2, 1), date(2024, 3, 1)]

# Build the full grid of partitions to backfill, then emit one ADD statement.
parts = partition_grid(
    sch,
    year=[2024],
    month=[d.month for d in months],
    region=["us", "eu"],
)
print(add_partitions_ddl("events", parts, "s3://my-bucket/events"))
```

`date_range` supports `"day"`, `"month"`, and `"year"` steps (for month/year the
day-of-month is anchored on the start date and clamped to each month). `partition_grid`
emits partitions in schema-column order and validates that every column is supplied.

## Manifests

A `Manifest` records which files belong to which partition for a dataset. It can
be serialized to lakeforge's own JSON layout (round-trippable via `from_json`),
or to the file-manifest format Redshift Spectrum / Athena accept.

```python
from lakeforge import Manifest, build_manifest, Partition, PartitionSchema

sch = PartitionSchema.parse("year:int,month:int,region")

m = Manifest(sch)
p1 = Partition.of(sch, year=2024, month=1, region="us")
m.add(p1, "s3://bucket/events/year=2024/month=1/region=us/part-0.parquet")
m.add(p1, "s3://bucket/events/year=2024/month=1/region=us/part-1.parquet")

m.total_files                 # 2
m.all_files()                 # [...two URIs in partition order...]

# Or build from (partition, files) pairs.
m2 = build_manifest(sch, [
    (Partition.of(sch, year=2024, month=2, region="eu"),
     ["s3://bucket/events/year=2024/month=2/region=eu/part-0.parquet"]),
])

# Serialize to lakeforge JSON and back.
text = m.to_json()
restored = Manifest.from_json(text)
assert restored.total_files == m.total_files

# Or to a Redshift Spectrum / Athena file manifest.
print(m.to_redshift_manifest())
```

```json
{
  "entries": [
    {
      "url": "s3://bucket/events/year=2024/month=1/region=us/part-0.parquet",
      "mandatory": true
    },
    {
      "url": "s3://bucket/events/year=2024/month=1/region=us/part-1.parquet",
      "mandatory": true
    }
  ]
}
```

## S3 discovery

`lakeforge.discovery` scans an S3 prefix and reconstructs the partitions (and
optionally a manifest) that physically exist, parsing each object key against
your schema. This requires the `aws` extra (`pip install "lakeforge[aws]"`).
`boto3` is imported lazily, so the rest of the library stays dependency-free.

```python
from lakeforge import PartitionSchema
from lakeforge.discovery import discover_partitions, discover_manifest

sch = PartitionSchema.parse("year:int,month:int,region")

# Uses the default boto3 S3 client unless you pass client=...
partitions = discover_partitions("my-bucket", "events/", sch)
for p in partitions:
    print(p.path())

# Collect the object keys under each partition into a manifest.
manifest = discover_manifest("my-bucket", "events/", sch)
print(manifest.total_files)
```

Keys that do not contain a full partition path (for example a stray
`events/_SUCCESS` marker) are skipped by default; pass `strict=True` to raise a
`PartitionParseError` instead. You can inject your own client via the `client=`
keyword, which is handy for testing with tools like
[`moto`](https://github.com/getmoto/moto):

```python
import boto3
from moto import mock_aws

from lakeforge import PartitionSchema
from lakeforge.discovery import discover_partitions

@mock_aws
def test_discovery():
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="my-bucket")
    for key in [
        "events/year=2024/month=1/region=us/part-0.parquet",
        "events/year=2024/month=2/region=eu/part-0.parquet",
        "events/_SUCCESS",  # skipped: no partition path
    ]:
        s3.put_object(Bucket="my-bucket", Key=key, Body=b"")

    sch = PartitionSchema.parse("year:int,month:int,region")
    partitions = discover_partitions("my-bucket", "events/", sch, client=s3)
    assert [p.path() for p in partitions] == [
        "year=2024/month=1/region=us",
        "year=2024/month=2/region=eu",
    ]
```

## CLI

Installing lakeforge provides a `lakeforge` command for common one-off tasks. Run
`lakeforge --help` (or `lakeforge <command> --help`) for full usage.

**Parse an S3 key into typed partition values:**

```console
$ lakeforge parse --schema "year:int,month:int,region" \
    "s3://bucket/events/year=2024/month=3/region=us/part-0.parquet"
{
  "year": 2024,
  "month": 3,
  "region": "us"
}
```

**Build a partition path from values:**

```console
$ lakeforge path --schema "year:int,month:int,region" year=2024 month=3 region=us
year=2024/month=3/region=us

$ lakeforge path --schema "year:int,month:int,region" --trailing-slash \
    year=2024 month=3 region=us
year=2024/month=3/region=us/
```

**Emit `ALTER TABLE ... ADD PARTITION` DDL:**

```console
$ lakeforge add-partition --schema "year:int,month:int,region" \
    --table events --database analytics --location s3://bucket/events \
    year=2024 month=3 region=us
ALTER TABLE analytics.events ADD IF NOT EXISTS PARTITION (year=2024, month=3, region='us') LOCATION 's3://bucket/events/year=2024/month=3/region=us/';
```

**Emit `CREATE EXTERNAL TABLE` DDL:**

```console
$ lakeforge create-table --schema "year:int,region" \
    --table events --database analytics --location s3://bucket/events \
    --column event_id=string --column payload=string
CREATE EXTERNAL TABLE IF NOT EXISTS analytics.events (
  event_id string,
  payload string
) PARTITIONED BY (year bigint, region string)
STORED AS PARQUET
LOCATION 's3://bucket/events/';
```

**List partitions present under an S3 prefix** (requires the `aws` extra):

```console
$ lakeforge discover --schema "year:int,month:int,region" \
    --bucket my-bucket --prefix events/
year=2024/month=1/region=us
year=2024/month=2/region=eu
```

Add `--strict` to fail on keys that do not parse into a full partition path.

## Development

```bash
# Create a virtualenv and install the package with its dev tooling.
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run the test suite.
pytest

# Lint and auto-fix with ruff.
ruff check .
ruff check --fix .

# Type-check (the project is fully typed and runs mypy in strict mode).
mypy lakeforge
```

The package ships a `py.typed` marker, so type information is available to
downstream users out of the box.

## License

`lakeforge` is released under the [MIT License](LICENSE). © 2026 Abdur Rehman Sarwar.
