# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-06-17

Initial release of **lakeforge**, a toolkit for Hive-partitioned data lakes on
S3: typed partition schemas, partition paths, predicate-based pruning,
Athena/Glue DDL generation, manifests, and optional S3 discovery, plus a CLI.

### Added

- **Partition schemas** (`lakeforge.schema`): typed, ordered partition column
  definitions via `PartitionColumn`, `PartitionSchema`, and the `ColumnType`
  enum (`string`, `int`, `double`, `boolean`, `date`, `timestamp`) with Athena
  type mapping. Schemas can be built with the `schema()` / `PartitionSchema.of()`
  helpers or parsed from a compact spec such as `"year:int,month:int,region"`,
  and they coerce raw string values to typed Python values.
- **Partitions and paths** (`lakeforge.partition`): the `Partition` type binds
  typed values to a schema and renders Hive-style partition paths
  (`year=2024/month=1`) and full S3 URIs, with percent-encoding of segment
  values for safe round-tripping. `Partition.parse()` reconstructs a partition
  from a path or S3 key, and `build_partitions()` builds partitions in bulk
  from value mappings.
- **Predicates** (`lakeforge.predicate`): a composable predicate algebra
  (`Eq`, `Ne`, `Gt`, `Ge`, `Lt`, `Le`, `In`, `Between`, `And`, `Or`, `Not`,
  `Always`) combinable with `&`, `|`, and `~`, plus a fluent `field()` /
  `PartitionField` DSL (e.g. `field("year") >= 2023`).
- **Partition pruning** (`lakeforge.pruning`): `prune()` filters partitions by a
  predicate, `validate_predicate()` checks that a predicate only references
  columns in the schema, and `count_pruned()` reports how many partitions a
  predicate eliminates.
- **Athena / Glue DDL** (`lakeforge.glue`): pure string builders for
  `CREATE EXTERNAL TABLE` (`create_table_ddl`), `ALTER TABLE ... ADD PARTITION`
  for single (`add_partition_ddl`) and batched (`add_partitions_ddl`)
  partitions, `MSCK REPAIR TABLE` (`msck_repair`), and Athena **partition
  projection** table properties (`projection_properties`) for integer, date,
  and enum projections.
- **Manifests** (`lakeforge.manifest`): `Manifest` and `PartitionFiles` map
  partitions to their files, with JSON serialization (`to_json` / `from_json`,
  `to_dict` / `from_dict`), a Redshift Spectrum / Athena file-list manifest
  exporter (`to_redshift_manifest`), and a `build_manifest()` helper.
- **S3 discovery** (`lakeforge.discovery`, optional): `discover_partitions()`
  and `discover_manifest()` scan an S3 prefix and reconstruct the partitions
  present, with a `strict` mode for unparseable keys. `boto3` is imported
  lazily and provided by the `aws` extra (`pip install lakeforge[aws]`).
- **Command-line interface** (`lakeforge.cli`): the `lakeforge` command with
  `parse`, `path`, `add-partition`, `create-table`, and `discover` subcommands.
- **Error hierarchy** (`lakeforge.errors`): `LakeForgeError` base class with
  `SchemaError`, `PartitionError`, `PartitionParseError`, `PredicateError`, and
  `DiscoveryError` subclasses.
- Typing support: ships a `py.typed` marker and is checked with `mypy --strict`.

[Unreleased]: https://github.com/AbdurRehmanSarwar/lakeforge/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/AbdurRehmanSarwar/lakeforge/releases/tag/v0.1.0
