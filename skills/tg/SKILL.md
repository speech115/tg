---
name: tg
description: Use when a task needs Telegram reads, searches, raw TL requests, media, or sends through the tg runtime.
---

# tg

Use the `tg` executable on PATH.

`tg` owns configuration, account selection, session locking, authentication,
and process errors. Telethon owns Telegram operations.

The default config is `~/.config/tg/config.toml`; set `TG_CONFIG` for another
file. Account names match `[A-Za-z0-9_-]+` and map directly to session basenames
under `~/.local/state/tg/`; omitting `--account` selects `main`.

```bash
tg doctor
tg script.py arg1 --flag
tg --account work script.py
tg skill
```

For a one-off program, pipe Python directly to `tg`:

```bash
tg <<'PY'
dialogs = await client.get_dialogs(limit=10)
for dialog in dialogs:
    print(dialog.name)
PY
```

Scripts receive `client`, `functions`, `types`, and the selected `account`.
Prefer a Telethon client method. Use `functions.*` and `types.*` for raw TL
requests when no friendly method fits.

## Minimize round trips

Bundle deterministic Telegram operations into one `tg` process and stop at a
genuine decision boundary, rather than starting one process per API call. Keep
workflow logic in the script, saving it when it becomes repetitive.

For sends that need retry control, choose and own a `random_id` in the script;
`tg` does not persist workflow state or idempotency state.

If a workflow becomes repetitive, save the Python program as a reusable script.
