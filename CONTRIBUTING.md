# Contributing

`tg` is intentionally small. The core owns configuration, named-session selection,
authentication, locking, and Python process semantics. Telethon owns Telegram operations.

## Scope

Before adding a core command or abstraction, first implement the workflow as ordinary
Python through `tg run`.

A new wrapper should require evidence that the same stable interaction is repeatedly
useful and meaningfully cheaper than a run script. Governors, workflow registries,
compatibility layers, persistent orchestration state, and Telegram-domain command trees
are out of scope without a separate architectural decision.

## Development

Requires Python 3.12+ and `uv`.

```bash
uv sync --locked --dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv build --no-sources
```

CI runs the same checks and smoke-tests the built wheel.

## Integration probes

The integration probes use a real authorized Telegram session and are not part of the
normal unit-test suite.

Read-only boundary probe:

```bash
tg run tests/integration/boundary_run.py
```

The send boundary probe mutates the explicitly selected target and cleans up its test
messages:

```bash
TG_SEND_BOUNDARY_TARGET=me tg run tests/integration/send_boundary.py
```

Do not point mutating probes at accounts or chats you are unwilling to modify.

## Release

The PyPI distribution name is `tg-harness`; the installed command remains `tg`.
The PyPI name `tg` is already used by another project.

Before the first release, configure a PyPI Trusted Publisher for:

- PyPI project: `tg-harness`
- GitHub owner: `speech115`
- repository: `tg`
- workflow: `release.yml`
- environment: `pypi`

For each release:

1. Update the version in `pyproject.toml` and `src/tg/__init__.py`.
2. Run `uv lock` and the full local checks.
3. Merge the green release change to `main`.
4. Create and push an annotated version tag, for example:

   ```bash
   git tag -a v0.1.0 -m v0.1.0
   git push origin v0.1.0
   ```

The release workflow builds and smoke-tests the wheel and source distribution,
publishes them to PyPI with Trusted Publishing, and then creates a GitHub Release.
