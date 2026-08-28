<img src="https://raw.githubusercontent.com/speech115/tg/main/static/banner-ink.svg" alt="tg-harness" width="100%" />

<div align="center">

# tg-harness

**A tiny authenticated Telegram harness for agents and humans.**

One Python process. One real Telegram account. The full Telethon surface.

</div>

`tg-harness` keeps the runtime deliberately small: configuration, named sessions,
authentication, locking, and Python process semantics. Telethon remains the Telegram
API.

Telethon is the API; `tg` only provides the authenticated execution boundary.
When a workflow is missing, write the missing logic as ordinary Python and run it
through `tg`.

```text
agent wants something in Telegram
        │
        ▼
      tg
        │
        ├── client.*        friendly Telethon methods
        └── functions.*     raw Telegram API when needed
```

**Three commands plus direct Python execution.**

```bash
tg login
tg doctor
tg skill
tg script.py
```

The Python distribution is `tg-harness`. The installed command is `tg`.

## Give it to your agent

Install from PyPI:

```bash
uv tool install tg-harness
```

Or install the current GitHub version:

```bash
uv tool install git+https://github.com/speech115/tg.git
```

Then give the agent this instruction:

```text
Use tg for Telegram. Run tg doctor first. For Telegram work, use one tg
program per decision boundary, prefer Telethon client methods, and fall back to
functions.* / types.* for raw Telegram requests.
```

Requires Python 3.12+ and a POSIX system (macOS or Linux).

## Configure once

Create Telegram API credentials at https://my.telegram.org/apps, then create
`~/.config/tg/config.toml`:

```toml
[telegram]
api_id = 123456
api_hash = "your-api-hash"
```

Set `TG_CONFIG` when the config lives elsewhere.

Authorize the default account:

```bash
tg login
tg doctor
```

The default account is `main`. Named accounts map directly to Telethon session files:

```bash
tg --account work login
tg --account work doctor
tg --account work script.py
```

```text
~/.local/state/tg/
├── main.session
├── work.session
└── another.session
```

Account names must match `[A-Za-z0-9_-]+`.

## Run ordinary Python

For a one-off task:

```bash
tg <<'PY'
dialogs = await client.get_dialogs(limit=10)
for dialog in dialogs:
    print(dialog.name)
PY
```

For reusable logic:

```bash
tg script.py arg1 --flag
tg --account work script.py arg1 --flag
```

Every run gets:

```python
client  # authenticated Telethon client
functions  # raw Telegram request constructors
types  # raw Telegram types
account  # selected named account
```

It also gets normal `__file__`, `sys.argv`, and local-import behavior.

Prefer the friendly API when it fits:

```python
messages = await client.get_messages("me", limit=20)
```

Drop to the raw API when it does not:

```python
result = await client(functions.users.GetFullUserRequest(id=types.InputUserSelf()))
```

## How it works

```text
                            one tg process
                                   │
                     authenticated Telethon client
                                   │
               ┌───────────────────┴───────────────────┐
               │                                       │
          client.* helpers                      raw TL requests
               │                                functions.* / types.*
               └───────────────────┬───────────────────┘
                                   │
                              Telegram API

config      ~/.config/tg/config.toml (or TG_CONFIG)
sessions    ~/.local/state/tg/<account>.session
locking     one process per named session
```

Workflow logic stays in ordinary Python scripts.

## Agent skill

The repository ships `skills/tg/SKILL.md`.

Use `tg skill` to print the bundled instructions. Its main rule is simple: bundle
deterministic operations into one `tg` process and stop only at a real decision
boundary. That avoids reconnecting for every API call and keeps agent behavior
both faster and simpler.

## Trust boundary

`tg` is intentionally **not a sandbox**.

Code passed to it has the permissions of the selected Telegram account and can read,
send, edit, delete, download, join, leave, and perform raw Telegram API operations.

Treat these as secrets:

- `api_hash`
- Telethon `.session` files
- any exported authorization material

The runtime keeps sessions outside the repository and serializes access to each named
session with a lock.

## Why it stays small

A missing Telegram capability is not a reason to add another core command.

Start with `tg`. If a workflow becomes repetitive, save the Python program as a
reusable script.

The intended core remains:

```text
login · doctor · skill · Python execution
```


## Development

```bash
git clone https://github.com/speech115/tg.git
cd tg

./tg doctor

uv sync --locked --dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv build --no-sources
uv run --isolated --no-project --with dist/*.whl tests/smoke_test.py
uv run --isolated --no-project --with dist/*.tar.gz tests/smoke_test.py
```

These local commands lint, test, build, and smoke-test both distributions. No
GitHub Actions runner is required.

See [CONTRIBUTING.md](CONTRIBUTING.md) for scope, integration probes, and release
instructions.

## License

MIT. See [LICENSE](LICENSE).
