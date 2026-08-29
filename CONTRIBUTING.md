# Contributing

`tg` is intentionally small: Telethon is the API and `tg` provides the authenticated
execution boundary.

## Scope

Implement workflows as ordinary Python through `tg` first. Extend the core only when
ordinary Python and Telethon cannot express the need cleanly.

## Development

Requires Python 3.12+ and `uv`.

```bash
uv sync --locked --dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

These checks run locally and do not require GitHub Actions.

## Integration probes

Integration probes use a real authorized Telegram session and are not part of the
normal unit-test suite:

```bash
tg tests/integration/runtime_probe.py
```
