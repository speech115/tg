# ADR-0001: Run-first Telegram capabilities

- Status: Accepted
- Date: 2026-08-27

## Decision

Implement a new Telegram capability first as ordinary Python passed to
`tg run`. Add a wrapper only after repeated use shows that a stable command
shape removes meaningful repeated agent or human code.

The core remains responsible for configuration, named-account selection,
session lifecycle, locking, and process semantics. `default_account` selects
the account used without `--account`; `tg --account NAME ...` selects another
configured session. Telethon remains the Telegram API. Workflow policy, bulk
orchestration, and domain-specific shortcuts stay at the run-script or wrapper
layer.

## Guardrails

- Prefer McCabe complexity at or below 8.
- Ruff `C901` is the hard ceiling at 12.
- Complexity is a control-flow signal, not an architecture verdict.
- Do not add a governor, workflow registry, or compatibility layer to the
  runtime without a separate decision and evidence.

## Consequence

`tg run` is the capability boundary; wrappers are earned by demonstrated
repeatability instead of being added speculatively.

The send probe only establishes deduplication for the tested same-process,
same-peer, same-payload retry. It does not establish a contract for a new
process or reconnect, the retention window, another peer, or a changed
payload with the same `random_id`.
