# ADR-0001: Python-first Telegram capabilities

- Status: Accepted
- Date: 2026-08-27

## Decision

Implement a new Telegram capability first as ordinary Python passed to
`tg`. Save that program as a script when the workflow becomes repetitive.

The core remains responsible for configuration, named-account selection,
session lifecycle, locking, and process semantics. Configuration defaults to
`~/.config/tg/config.toml` and can
be overridden with `TG_CONFIG`. The account name is the session basename under
`~/.local/state/tg/`; `main` is selected when
`--account` is omitted, and `tg --account NAME ...` selects another session.
Telethon remains the Telegram API. Workflow policy, bulk orchestration, and
domain-specific shortcuts stay at the run-script or wrapper layer.

## Guardrails

- Prefer McCabe complexity at or below 8.
- Ruff `C901` is the hard ceiling at 12.
- Complexity is a control-flow signal, not an architecture verdict.
- Do not add a governor, workflow registry, or compatibility layer to the
  runtime without a separate decision and evidence.

## Consequence

`tg` is the capability boundary; workflow scripts stay outside the runtime.

The send probe only establishes deduplication for the tested same-process,
same-peer, same-payload retry. It does not establish a contract for a new
process or reconnect, the retention window, another peer, or a changed
payload with the same `random_id`.
