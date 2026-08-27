---
name: tg
description: Use when a task needs Telegram reads, searches, raw TL requests, media, or sends through the tg runtime.
---

# tg

Use the `tg` executable on PATH.

`tg` owns configuration, account selection, session locking, authentication,
and process errors. Telethon owns Telegram operations.

Account names match `[A-Za-z0-9_-]+` and map directly to session basenames under
`~/.local/state/tg/`; omitting `--account` selects `main`.

```bash
tg doctor
tg run script.py arg1 --flag
tg --account work run script.py
```

`tg run` exposes `client`, `functions`, `types`, and the selected `account`.
Prefer a Telethon client method. Use `functions.*` and `types.*` for raw TL
requests when no friendly method fits.

## Minimize round trips

Bundle deterministic Telegram operations into one `tg run` and stop at a genuine
decision boundary, rather than starting one process per API call. Keep one-off
workflow logic in the run script. Add a wrapper only after the same script shape is
repeatedly useful.

For sends that need retry control, choose and own a `random_id` in the run script;
`tg` does not persist workflow state or idempotency state.
