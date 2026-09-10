<img src="https://raw.githubusercontent.com/speech115/tg/main/static/banner-ink.svg" alt="tg" width="100%" />

<div align="center">

# tg

**A tiny authenticated Telegram harness for agents and humans.**

One Python process. One authenticated Telegram account per run. The full Telethon surface.

</div>

`tg` keeps the runtime deliberately small: configuration, named sessions,
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
Use tg for Telegram. Read tg skill. Run tg doctor for initial setup or diagnosis,
not before every task. Ask me to handle login if authorization is missing; a busy
session is not an authorization failure. Use one tg program per decision boundary,
prefer client methods, and fall back to functions.* / types.* for raw requests.
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

Keep the config readable only by your user:

```bash
chmod 600 ~/.config/tg/config.toml
```

Alternatively, set `TG_API_ID` and `TG_API_HASH` in the environment.

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

## Concurrent agents

A named session still has exactly one owner. A competing invocation now waits
**up to 120 seconds by default**, without constructing a Telegram client or
connecting to Telegram. It reports the wait once on stderr, leaving stdout for
script output. The timeout covers lock acquisition, not script execution.

```bash
tg script.py                       # wait up to 120 seconds
tg --lock-timeout 300 script.py    # allow a longer wait
tg --lock-timeout 0 script.py      # fail immediately if busy
```

Put runtime options before the command or script name. The wait is cancellable
with Ctrl+C, is not FIFO, and never steals a lock. The lock file contains a
best-effort owner PID for diagnosis; a leftover PID/file does not mean a lock
is held. Do not delete `.lock` files or kill another agent to bypass contention.
The OS releases the lock when its owning file descriptors close.

For a download and a read to run simultaneously, set up **two independent
Telegram authorizations** for the same profile. Choose an unused local name
and log in manually with the same phone number, never by copying `.session`
files or exporting the same authorization key:

```bash
tg --account main_media login
tg --account main doctor
tg --account main_media doctor
```

Check that both `doctor` outputs have the same `user=ok id=...`. After that
one-time check, assign short reads to `main` and downloads to `main_media`:

```bash
tg read.py
tg --account main_media download.py
```

`read.py` and `download.py` are your own ordinary Python scripts. Tasks using the
same name still wait for each other. There is no automatic session pool, identity
matching, or account switching. Agents must use only explicitly approved sessions.

Save fetched data and exit `tg` before local analysis, transcription, or other
non-Telegram work. Keep concurrency low and respect Telethon's `FloodWait` handling;
do not rotate sessions to bypass a wait. This change preserves Telethon's built-in
waits but does **not** add an account-wide rate limiter or coordinate waits across
independent sessions. Separate sessions do not guarantee immunity from restrictions.
See the [Telethon FAQ](https://docs.telethon.dev/en/stable/quick-references/faq.html).

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

The repository ships `src/tg/SKILL.md`.

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

See [CONTRIBUTING.md](CONTRIBUTING.md) for development and integration instructions.

## License

MIT. See [LICENSE](LICENSE).
