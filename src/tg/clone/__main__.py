"""Offline inspection and export; never opens a Telegram session or configuration."""

import argparse
import json
import os
from pathlib import Path

from .engine import source_matches
from .state import Store
from .support import PolicyError, encode, replace_text


def _progress(value):
    if not value or value.get("status") != "running":
        return value
    try:
        os.kill(value["pid"], 0)
    except ProcessLookupError:
        return {**value, "status": "interrupted"}
    return value


def status(store, source=None, account_id=None):
    rows = []
    for clone in store.all():
        if not source_matches(clone, source) or (
            account_id and clone.account_user_id != account_id
        ):
            continue
        outcomes = store.conn.execute(
            "SELECT json_extract(data,'$.status'), count(*) FROM outcomes WHERE clone=? "
            "GROUP BY json_extract(data,'$.status')",
            (clone.clone_id,),
        ).fetchall()
        losses = [
            {"leg": leg, "source_id": source_id, **json.loads(raw)}
            for leg, source_id, raw in store.conn.execute(
                "SELECT leg,source,data FROM outcomes WHERE clone=? "
                "AND json_extract(data,'$.status') != 'copied' ORDER BY source DESC LIMIT 20",
                (clone.clone_id,),
            )
        ]
        vote = store.conn.execute(
            "SELECT data FROM votes WHERE clone=?", (clone.clone_id,)
        ).fetchone()
        cooldown = store.conn.execute(
            "SELECT deadline FROM cooldowns WHERE account=?", (clone.account_user_id,)
        ).fetchone()
        rows.append(
            {
                "clone_id": clone.clone_id,
                **clone.metadata(),
                "progress": _progress(clone.progress),
                "mapped": {
                    "posts": len(clone.id_map),
                    "comments": len(clone.discussion_id_map),
                    "topics": len(clone.topic_map),
                },
                "outcomes": dict(outcomes),
                "recent_losses": losses,
                "pending": store.pending(clone.clone_id),
                "pending_vote": json.loads(vote[0]) if vote else None,
                "cooldown_until": cooldown[0] if cooldown else None,
            }
        )
    return rows


def export(store, source, account_id=None):
    matches = status(store, source, account_id)
    if len(matches) != 1:
        raise PolicyError("export requires exactly one clone; use its clone ID")
    clone = store.load(matches[0]["clone_id"])
    return clone.artifact()


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m tg.clone")
    parser.add_argument("operation", choices=("status", "export"))
    parser.add_argument("source", nargs="?")
    parser.add_argument("--account-id", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    with Store(readonly=True) as store:
        result = (
            status(store, args.source, args.account_id)
            if args.operation == "status"
            else export(store, args.source, args.account_id)
        )
        rendered = encode(result) + "\n"
    if args.output:
        replace_text(args.output, rendered)
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
