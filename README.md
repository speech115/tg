# tg

Thin authenticated Telegram runtime on top of Telethon.

`tg` owns configuration, session lifecycle, locking, and process errors. Telethon remains the Telegram API. New workflows start as ordinary Python passed to `tg run`; a shortcut is added only when the same interaction becomes frequent and benefits from a stable shape.

## Status

The first slice is the runtime spike:

```bash
tg login
tg run -
```

Inside a run script, the runtime provides `client`, `functions`, `types`, and `account`.

```python
dialogs = await client.get_dialogs(limit=10)
for dialog in dialogs:
    print(dialog.name)
```

`tg run` is a trusted full-account surface. It is not a sandbox.

## Configuration

Create `~/.config/tg/config.toml`:

```toml
[telegram]
api_id = 123456
api_hash = "your-api-hash"
session = "~/.local/state/tg/main"
account = "main"
```

The session and lock live outside the repository. Never commit API credentials or Telethon session files.

## Development

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
```
