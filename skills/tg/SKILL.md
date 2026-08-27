---
name: tg
description: Use when a task needs Telegram reads, searches, raw TL requests, media, or sends through this repository's tg runtime.
---

# tg

Use the repository runtime at `/Users/sereja/Projects/tools/tg/.venv/bin/tg`.

`tg` owns configuration, account selection, session locking, authentication,
timeouts, and process errors. Telethon owns Telegram operations.

```bash
tg doctor
tg run script.py arg1 --flag
tg --account work run script.py
```

`tg run` exposes `client`, `functions`, `types`, and the selected `account`.
Prefer a Telethon client method. Use `functions.*` and `types.*` for raw TL
requests when no friendly method fits. Keep one-off workflow logic in the run
script. Add a wrapper only after the same script shape is repeatedly useful.

For sends that need retry control, choose and own a `random_id` in the run
script; `tg` does not persist workflow state or idempotency state.
