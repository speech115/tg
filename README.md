# tg

Thin authenticated Telegram runtime on top of Telethon.

`tg` owns configuration, named sessions, authentication, locking, and process semantics.
Telethon remains the Telegram API. Instead of growing a second Telegram command API, `tg run`
executes ordinary Python with an authenticated Telethon client.

The public Python distribution is `tg-runtime`; the installed command is `tg`.

## Install

Requires Python 3.12+ and a POSIX system (macOS or Linux).

```bash
uv tool install tg-runtime
```

Or install the current GitHub version:

```bash
uv tool install git+https://github.com/speech115/tg.git
```

## Configure

Create Telegram API credentials at https://my.telegram.org/apps, then create
`~/.config/tg/config.toml`:

```toml
[telegram]
api_id = 123456
api_hash = "your-api-hash"
```

Treat the API hash and session files as credentials. Sessions live under
`~/.local/state/tg/` and never need to be stored in the repository.

Authorize the default `main` account and verify it:

```bash
tg login
tg doctor
```

Named accounts map directly to session files. Account names must match
`[A-Za-z0-9_-]+`:

```bash
tg --account work login
tg --account work doctor
```

`main` uses `~/.local/state/tg/main.session`; `--account work` uses
`~/.local/state/tg/work.session`.

## Run Telegram code

Use stdin for one-off work:

```bash
tg run - <<'PY'
dialogs = await client.get_dialogs(limit=10)
for dialog in dialogs:
    print(dialog.name)
PY
```

Or run a normal Python file with arguments:

```bash
tg run script.py arg1 --flag
tg --account work run script.py arg1 --flag
```

A run script receives `client`, `functions`, `types`, and the selected `account`.
It also gets normal `__file__`, `sys.argv`, and local-import behavior.

Prefer Telethon client methods:

```python
messages = await client.get_messages("me", limit=20)
```

When needed, use the raw Telegram API directly:

```python
result = await client(
    functions.users.GetFullUserRequest(id=types.InputUserSelf())
)
```

`tg run` is a trusted full-account execution surface, not a sandbox. Code passed to it can
read, send, edit, delete, download, and otherwise act with the permissions of the selected
Telegram account.

## Design

The core surface is intentionally limited to:

```text
tg login
tg doctor
tg run
```

New Telegram workflows belong in ordinary `tg run` Python. A wrapper is added only when a
repeated workflow has a stable shape and materially benefits from one.

The repository also includes `skills/tg/SKILL.md` for coding agents.

## Development

```bash
git clone https://github.com/speech115/tg.git
cd tg
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv build
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for project scope, integration probes, and releases.

## License

MIT. See [LICENSE](LICENSE).
