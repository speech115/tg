"""Resumable cloning through an existing authenticated Telethon client."""

import argparse
import os
import sys
import time

from telethon import errors

from . import engine, roster, snapshot
from .state import Store
from .support import PolicyError, encode

__all__ = ["Store", "run"]


def parser():
    result = argparse.ArgumentParser(prog="tg workflows/clone.py")
    commands = result.add_subparsers(dest="operation", required=True)
    for name in ("init", "sync", "refresh", "roster"):
        command = commands.add_parser(name)
        command.add_argument("source")
        if name in ("init", "refresh"):
            command.add_argument("--commit", metavar="PREVIEW_ID")
        if name == "init":
            command.add_argument("--replace", action="store_true")
            command.add_argument("--no-comments", action="store_true")
        if name == "sync":
            command.add_argument("--limit", type=int, help="maximum complete batches")
            command.add_argument(
                "--max-runtime", type=float, help="seconds; finish the current batch"
            )
            command.add_argument(
                "--capture-poll-votes",
                action="store_true",
                help="temporarily vote in eligible anonymous polls, then retract",
            )
    return result


async def _dispatch(client, store, me, args):
    if args.operation in ("init", "refresh"):
        if args.commit:
            payload = store.consume_preview(args.commit, f"clone-{args.operation}", me.id)
            commit = engine.commit_init if args.operation == "init" else engine.commit_refresh
            return await commit(client, store, me, args.source, payload)
        if args.operation == "init":
            return await engine.preview_init(
                client, store, me, args.source, replace=args.replace, no_comments=args.no_comments
            )
        return await engine.preview_refresh(client, store, me, args.source)
    if args.operation == "sync":
        return await engine.sync_text(
            client,
            store,
            me,
            args.source,
            limit=args.limit,
            max_runtime=args.max_runtime,
            capture_poll_votes=args.capture_poll_votes,
        )
    _, source, _, clone = await engine._load_refresh_context(client, store, me, args.source)
    clone.participants = await roster.collect(client, clone, source)
    clone.save()
    return {"clone_id": clone.clone_id, "participants": clone.participants}


def _finish_progress(store, account_id, status, error=None):
    for clone in store.all():
        progress = clone.progress or {}
        if (
            clone.account_user_id != account_id
            or progress.get("pid") != os.getpid()
            or progress.get("status") != "running"
        ):
            continue
        clone.progress = {**progress, "status": status, "updated_at": time.time(), "error": error}
        clone.save()


async def run(client, argv=None, *, state_root=None):
    """Run an online operation; returns JSON-serializable data, prints nothing to stdout.

    ``state_root`` is injectable for isolated tests. Normal use always selects ~/.local/state/tg.
    """
    args = parser().parse_args(sys.argv[1:] if argv is None else argv)
    if args.operation == "init" and args.commit and (args.replace or args.no_comments):
        raise PolicyError("replace and no-comments options belong on the preview command")
    if args.operation == "sync":
        if args.limit is not None and args.limit < 1:
            raise PolicyError("limit must be positive")
        if args.max_runtime is not None and (not 0 < args.max_runtime < float("inf")):
            raise PolicyError("max-runtime must be finite and positive")
    me = await client.get_me()
    if me is None:
        raise PolicyError("Telegram client is not authorized")
    threshold = client.flood_sleep_threshold
    client.flood_sleep_threshold = 0
    try:
        with Store(state_root) as store, store.lock(me.id):
            store.cooldown(me.id)
            try:
                await snapshot.recover_votes(client, store, me.id)
                result = await _dispatch(client, store, me, args)
            except errors.FloodWaitError as error:
                _finish_progress(store, me.id, "cooldown", str(error))
                store.cooldown(me.id, error.seconds)
                raise
            except BaseException as error:
                _finish_progress(store, me.id, "stopped", str(error))
                raise
            _finish_progress(store, me.id, "paused" if result.get("remaining") else "complete")
            return result
    finally:
        client.flood_sleep_threshold = threshold


async def main(client):
    print(encode(await run(client)))
