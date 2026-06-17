# Contributing to lakeforge

Thanks for your interest in improving **lakeforge**, a toolkit for
Hive-partitioned data lakes on S3. This guide covers how to set up a
development environment, run the checks, and submit changes.

## Development environment

lakeforge targets Python 3.9+ and has no required runtime dependencies. The
optional AWS-backed features (S3 discovery) need `boto3`, which is installed as
part of the `dev` extra.

Create and activate a virtual environment, then install the package in editable
mode with the development dependencies:

```bash
python -m venv .venv
source .venv/bin/activate        # on Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

The `dev` extra pulls in everything you need to work on the project: `pytest`,
`pytest-cov`, `boto3`, `moto[s3]` (for mocking S3 in tests), `ruff`, and `mypy`.

If you only need the AWS runtime dependency without the rest of the toolchain,
install the `aws` extra instead:

```bash
pip install -e ".[aws]"
```

## Running the test suite

Tests live under `tests/` and use `pytest`. S3 interactions are mocked with
`moto`, so the suite runs fully offline and needs no AWS credentials.

```bash
pytest
```

To run a single test module or test:

```bash
pytest tests/test_partition.py
pytest tests/test_partition.py::test_parse_round_trip
```

To measure coverage (coverage is configured in `pyproject.toml` to track the
`lakeforge` package with branch coverage and `show_missing`):

```bash
pytest --cov
```

## Linting

Linting and import sorting are handled by [Ruff](https://docs.astral.sh/ruff/).
The configuration in `pyproject.toml` uses a line length of 100, targets Python
3.9, and enables the `E`, `F`, `I`, `UP`, `B`, `C4`, and `SIM` rule sets.

```bash
ruff check .
```

Many findings can be fixed automatically:

```bash
ruff check --fix .
```

## Type checking

The codebase is fully typed (it ships a `py.typed` marker) and is checked with
[mypy](https://mypy.readthedocs.io/) in `strict` mode (with
`warn_unused_ignores` enabled):

```bash
mypy lakeforge
```

New code should type-check cleanly under `strict`. Avoid blanket
`# type: ignore` comments; if one is unavoidable, scope it to a specific error
code (e.g. `# type: ignore[override]`).

## Pull request guidelines

Before opening a pull request, please make sure that:

- All three checks pass locally: `pytest`, `ruff check .`, and
  `mypy lakeforge`.
- New behavior is covered by tests, and bug fixes include a regression test.
- Public API changes are reflected in docstrings and, where relevant, the
  `README.md`.
- A note describing your change is added to the **Unreleased** section of
  `CHANGELOG.md` (see "Code style" below for the categories).
- The change is focused; keep unrelated refactors in separate PRs.

When you open the PR:

- Give it a clear, descriptive title and explain *what* changed and *why* in
  the body.
- Link any related issues (e.g. `Closes #123`).
- Keep commits logically scoped; squash noisy work-in-progress commits before
  requesting review.

## Code style

- Follow the existing style; Ruff and mypy are the source of truth, and the
  line length is 100 characters.
- Modules use `from __future__ import annotations` and prefer modern typing
  syntax (e.g. `list[str]`, `X | None`) since the codebase is `pyupgrade`-clean
  (the `UP` rule set).
- Public functions, classes, and modules carry concise docstrings; many include
  a short runnable example.
- Every error raised by the library derives from `LakeForgeError`, so callers
  can catch the whole package with one `except`. Raise the most specific
  subclass (`SchemaError`, `PartitionParseError`, `PredicateError`,
  `DiscoveryError`, ...) for new error conditions.
- Keep AWS/`boto3` imports lazy (inside functions) so the core library has no
  hard AWS dependency, mirroring `lakeforge/discovery.py`.
- Update `__all__` when you add or rename a public symbol.

By contributing, you agree that your contributions are licensed under the
project's MIT License.
