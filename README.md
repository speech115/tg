# tg

Thin authenticated Telegram runtime on top of Telethon.

`tg` owns configuration, session lifecycle, locking, and process errors. Telethon remains the Telegram API. New workflows start as ordinary Python passed to `tg run`; a shortcut is added only when the same interaction becomes frequent and benefits from a stable shape.

## Status

The current surface is intentionally small:

```bash
tg login
tg doctor
tg run -
```

Choose a named account before a command; the default account is `main`:

```bash
tg run script.py arg1 --flag
tg --account work run script.py arg1 --flag
```

Inside a run script, the runtime provides `client`, `functions`, `types`, and the selected
`account`. The script also receives normal `__file__`, `sys.argv`, and local-import semantics.

An account name must match `[A-Za-z0-9_-]+` and is the basename of its Telethon session under
`~/.local/state/tg/`.
`main` therefore uses `main.session`, and `--account work` uses `work.session`.

```python
dialogs = await client.get_dialogs(limit=10)
for dialog in dialogs:
    print(dialog.name)
```

`tg run` is a trusted full-account surface. It is not a sandbox.

## Boundary probe

Run the checked-in integration probe through the same public boundary:

```bash
tg run tests/integration/boundary_run.py
```

The default probe keeps one connection open while it reads dialogs and messages, searches Saved Messages, performs a raw TL request, downloads one small photo/document when available, runs a large local loop, and checks timeout and FloodWait handling. It never sends anything.

Process-boundary cases are explicit:

```bash
TG_BOUNDARY_MODE=floodwait tg run tests/integration/boundary_run.py  # exit 1
TG_BOUNDARY_MODE=exception tg run tests/integration/boundary_run.py  # exit 1
TG_BOUNDARY_MODE=hang tg run tests/integration/boundary_run.py  # Ctrl-C; exit 130
```

Sending requires both an explicit target and text:

```bash
TG_BOUNDARY_MODE=send TG_BOUNDARY_SEND_TO=me TG_BOUNDARY_SEND_TEXT="boundary probe" \
  tg run tests/integration/boundary_run.py
```

## Send boundary experiment

Keep send separate from the read-only probe:

```bash
TG_SEND_BOUNDARY_TARGET=me tg run tests/integration/send_boundary.py
```

The experiment sends one text and one file, retries one raw TL message with the same `random_id`, and simulates losing the response after the underlying request has returned. It reads back exact unique markers, verifies one message for each retry, and deletes the test messages. The simulated response loss is an idempotency-boundary check, not a claim about packet loss on a real network.

## Configuration

Create `~/.config/tg/config.toml`:

```toml
[telegram]
api_id = 123456
api_hash = "your-api-hash"
```

The session and lock live outside the repository. Never commit API credentials or Telethon session files.

## Development

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
```
