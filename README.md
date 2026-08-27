<div align="center">

# tg-harness

**A tiny authenticated Telegram harness for agents and humans.**

One Python process. One real Telegram account. The full Telethon surface.

</div>

`tg-harness` keeps the runtime deliberately small: configuration, named sessions,
authentication, locking, and process semantics. Telethon remains the Telegram API.

There is no second Telegram framework to learn and no growing tree of commands.
When a workflow is missing, write the missing logic as ordinary Python and run it
through `tg`.

```text
agent wants something in Telegram
        │
        ▼
      tg run
        │
        ├── client.*        friendly Telethon methods
        └── functions.*     raw Telegram API when needed
```

**Three commands. The whole Telethon surface.**

```bash
tg login
tg doctor
tg run -
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
Use tg for Telegram. Run tg doctor first. For Telegram work, use one tg run
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

Authorize the default account:

```bash
tg login
tg doctor
```

The default account is `main`. Named accounts map directly to Telethon session files:

```bash
tg --account work login
tg --account work doctor
tg --account work run script.py
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
tg run - <<'PY'
dialogs = await client.get_dialogs(limit=10)
for dialog in dialogs:
    print(dialog.name)
PY
```

For reusable logic:

```bash
tg run script.py arg1 --flag
tg --account work run script.py arg1 --flag
```

Every run gets:

```python
client      # authenticated Telethon client
functions   # raw Telegram request constructors
types       # raw Telegram types
account     # selected named account
```

It also gets normal `__file__`, `sys.argv`, and local-import behavior.

Prefer the friendly API when it fits:

```python
messages = await client.get_messages("me", limit=20)
```

Drop to the raw API when it does not:

```python
result = await client(
    functions.users.GetFullUserRequest(id=types.InputUserSelf())
)
```

## How it works

```text
                            one tg run process
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

config      ~/.config/tg/config.toml
sessions    ~/.local/state/tg/<account>.session
locking     one process per named session
```

`tg` owns only the runtime boundary. Workflow policy, bulk orchestration,
domain-specific shortcuts, and idempotency state stay outside the core.

## Agent skill

The repository ships `skills/tg/SKILL.md`.

Its main rule is simple: bundle deterministic operations into one `tg run` and
stop only at a real decision boundary. That avoids reconnecting for every API call
and keeps agent behavior both faster and simpler.

## Trust boundary

`tg run` is intentionally **not a sandbox**.

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

Start with `tg run`. Add a wrapper only if repeated real usage proves that a stable
command shape removes meaningful repeated work.

The intended core remains:

```text
login
doctor
run
```

No workflow registry. No local Telegram database. No governor. No parallel API layer
on top of Telethon.

## Development

```bash
git clone https://github.com/speech115/tg.git
cd tg

uv sync --locked --dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv build --no-sources
```

CI checks Linux and macOS, then builds and smoke-tests both wheel and source
distribution.

See [CONTRIBUTING.md](CONTRIBUTING.md) for scope, integration probes, and release
instructions.

## License

MIT. See [LICENSE](LICENSE).
