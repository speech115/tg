# Clone workflow

Clone channels, groups, forums, private conversations and bot histories through an
already authenticated Telethon client. A forum gets a private forum destination;
other source types get a private broadcast channel. Linked channel discussions get
a separate private group.

## Direct Python API

`tg` supplies authentication; `tg.clone` supplies the durable copying workflow.
Neither the workflow nor an agent should open a second Telegram client.

```python
from tg.clone import clone

preview = await clone(client, "channel:123456789")
```

A preview creates no Telegram destinations or copied messages. After checking the
source, the explicit write call both initializes and copies, or resumes saved work:

```python
result = await clone(
    client,
    "channel:123456789",
    commit=True,
    limit=50,  # complete batches; an album stays whole
    max_runtime=600,  # seconds; finish the current batch
)
print(result)
```

Save that code as `clone.py` and run `tg clone.py`, or pass it through `tg` stdin.
No repository checkout is required for the installed package. Repeat the call with
the same source to continue; an initialized clone does not repeat title/profile,
folder or notification setup. An interrupted initialization is completed first.

`replace=True` deliberately archives local state and creates a **new** clone. Use
it only for that explicit one-time action, not on every resume. `no_comments=True`
selects posts-only initialization; it cannot disable an already linked discussion.
`capture_poll_votes=True` remains an explicit opt-in for temporary votes. All these
switches require actual booleans. `state_root` exists for isolated tests; normal
calls use the standard state directory.

This API uses the caller's `commit=True` as publication consent; it does not consume
a previously issued preview token. A workflow that needs a five-minute, single-use,
account-bound approval must retain the `run` preview/commit interface below.
Every online entry also completes a previously authorized pending vote retraction
before other work, including when the requested operation is a preview.

## Compatibility: run from this checkout


```bash
.venv/bin/tg workflows/clone.py init channel:123456789
.venv/bin/tg workflows/clone.py init channel:123456789 --commit PREVIEW_ID
.venv/bin/tg workflows/clone.py sync channel:123456789 --limit 50
.venv/bin/tg workflows/clone.py sync channel:123456789
```

The first command returns a preview and creates no Telegram peers. Its token expires
in five minutes and can be committed once, by the same Telegram account. Put
`--replace` and `--no-comments` on the preview command when needed.

Use `channel:ID`, `chat:ID` or `user:ID` to avoid ambiguity between Telegram peer
classes. Usernames and Telegram's marked numeric IDs also work. For an initialized
clone, `sync`, `refresh` and `roster` can use its clone ID or an unambiguous part of
its saved source title. Account selection remains the outer harness's job:

```bash
.venv/bin/tg --account work workflows/clone.py sync channel:123456789
```

`--limit` counts whole batches: an album is one batch. `--max-runtime SECONDS` stops
between batches and finishes the current album, including its downloads. Both leave
saved cursors for the next `sync`. The result's `remaining` field says whether a cap
stopped the run. This is a one-shot workflow; it does not start background jobs.

## Installed package

The implementation ships in the `tg-harness` wheel as `tg.clone`. For compatibility, save this script as
`clone.py` and run it with `tg clone.py init|sync|refresh|roster SOURCE [options]`:

```python
from tg.clone import main

await main(client)
```

For a larger Python workflow, use the same interface without printing its result:

```python
from tg.clone import run

result = await run(client, ["sync", "channel:123456789", "--limit", "50"])
```

The runtime still has three built-in commands (`login`, `doctor`, `skill`). There
is no separate `tg clone` command or second authentication layer.

## Inspect without Telegram

```bash
.venv/bin/python -m tg.clone status
.venv/bin/python -m tg.clone status channel:123456789 --account-id 987654321
.venv/bin/python -m tg.clone export CLONE_ID --output clone-state.json
```

These commands read local state without configuration, authentication or network
access. `status` includes separate post/comment cursors, mapping counts, current
phase/file/bytes, pending sends, rate-limit deadlines and the latest 20 skipped or
degraded outcomes. `export` includes every mapping, outcome, event and unresolved
send. Participant snapshots remain in the path reported by `participants.path`.

## Other operations

```bash
.venv/bin/tg workflows/clone.py roster channel:123456789
.venv/bin/tg workflows/clone.py refresh channel:123456789
.venv/bin/tg workflows/clone.py refresh channel:123456789 --commit PREVIEW_ID
.venv/bin/tg workflows/clone.py init channel:123456789 --replace
```

Participants are collected after the first complete history sync. `roster` explicitly
refreshes that snapshot. Telegram access refusals are recorded as unavailable.

`refresh` previews missing attribution prefixes on already copied posts. Commit
rechecks the saved mapping and current destination text before editing; manually
changed text and existing native forward headers are left alone. It is not a general
mirror of later source edits or deletions.

`init --replace` previews a new destination. Commit archives the old mappings and
outcomes locally and starts a fresh clone; the previous Telegram peers remain.
Finish pending poll-vote recovery before replacing a clone.

## Content handling

| Content | Behavior |
|---|---|
| Messages and albums | Copied in source order, with one atomic mapping commit per complete batch. |
| Replies and quotes | Remapped within the clone; accessible foreign quotes stay native. A definite refusal produces a recorded fallback. |
| Photos and documents | Forwarded when possible. Replies can reuse Telegram media references. Protected sources use resumable downloads and uploads when Telegram permits. |
| Video, voice, audio, stickers, files | Document attributes, MIME type and available still thumbnails are preserved on upload. Spoiler flags are preserved. |
| Reposted messages | The original is forwarded only after matching source content, formatting, media and buttons; otherwise a text attribution is used. |
| Comments | Posts and discussions interleave in windows of 50 batches; comments wait for unmapped parent posts. Existing progress survives lost discussion access. |
| Forums | Topic titles and icons are recreated; replies retain destination topic placement. |
| Polls and stories | Text snapshots. Unavailable poll breakdowns and stories are explicitly identified. |
| Unsupported or expiring media | Skipped with a durable reason. Albums are never partially published. |
| Bot keyboards | Native forwards may retain them; copied messages record the dropped buttons. |
| Profiles, pins, folders | Titles, descriptions and avatars are copied; destinations are muted and added to Clone. Existing destination pins are preserved. |

Poll snapshots do not vote by default. `sync --capture-poll-votes` explicitly enables
a temporary vote to reveal results in eligible anonymous polls, followed by a
retraction. Public, closed, quiz, non-retractable and hidden-results polls are
excluded. The recovery record is saved before voting. If retraction fails, the next
online operation must retract it before doing other clone work.

## State and recovery

All workflow state lives under `~/.local/state/tg/clone/`; configuration and sessions
remain owned by `tg`. There is one SQLite connection per operation, WAL with FULL
synchronization, and an operation lock keyed by the actual Telegram user ID.
Message maps are queried in SQLite without loading the whole history into Python.

Before a publish request, the workflow saves its source identity and `random_id`
values. A complete Telegram receipt is saved before committing mappings, cursors and
outcomes together. A restart can finish a saved receipt without publishing again.
An unconfirmed request retains its original IDs; a changed source or an unexpected
destination tail stops the run for inspection. A lost server response does not prove
delivery, so this is not an exactly-once guarantee.

Completed and partial downloads are keyed by typed source peer, message, media type,
media ID and byte size. A same-size replacement cannot reuse another file's cache.
Checkpoints are written only after the downloaded bytes are synced to disk. Uploads
use at most four workers and publication remains sequential.

A Telegram FloodWait is saved for the account and ends the operation. Subsequent
runs refuse early until the deadline. The supplied client's sleep threshold is
restored afterward. Clone state from the old CLI is not imported or migrated.

## Implementation boundaries

The runtime in `tg.cli`, `tg.config` and `tg.session` is unchanged. The direct Python
entry and the compatibility argument parser share one operation boundary: account
lock, Store, cooldown, pending-vote recovery and progress cleanup.

The copy path is `engine` → `replies` / `quotes` → `send` → `publish` / `state`.
Replies are classified once per batch and the result travels in the transport plan;
comment batches reuse that same plan. `discussion` yields read events instead of
owning a second callback-based copy loop. `media` owns download/upload checkpoints
and native media attributes. `CloneState.leg()` exposes the posts or discussion map.

Related private helpers were consolidated: `transport` into `replies`,
`quote_fallback` into `quotes`, `fidelity` into `batching`, and `transfer` / `reupload`
into `media`. These private import paths are not compatibility APIs. The supported
`clone`, `run`, `Store`, checkout wrapper, offline commands and their recovery
behavior remain available.

Saved workflow state from the earlier `codex/clone-workflow` implementation is still
readable. The new `initialized` metadata flag defaults to false for older records;
the next direct write call safely completes initialization once without discarding
maps. This is not an importer for the different `tgcli` state format.

## Verification

The tests use real Telethon request/message types and an in-memory Telegram
service. They cover source types, initialization, albums, comments, topics, media,
quotes, snapshots, previews, rate limits, interrupted transfers and crash recovery.

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

The earlier migration documented a private live smoke test that verified 78 channel messages, seven albums and five
comments, including text/entities, media identities, audio/video attributes and
discussion placement. Initialization recovered from a creation FloodWait. A stop
after an album receipt but before its mapping commit resumed without duplicate
messages. Comments were sampled separately because the source clone stored hundreds
of automatic forwards before its first comment.

The refactor was verified with the local fake service and packaging checks; it did
not run a new live Telegram test. The earlier live test covers forwarding and media-reference reuse. Protected reuploads,
forums and poll snapshots remain covered by local tests, not this live sample.

Adapted from the MIT-licensed
[`speech115/tgcli` clone module at e12a2bd](https://github.com/speech115/tgcli/tree/e12a2bd7cdeeeed6fe4dc078464d8b2e22da5c12).
The copyright and license are retained in the repository's [LICENSE](../LICENSE).
