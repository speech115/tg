"""One SQLite connection per operation; maps stay in SQLite, not Python heaps."""

import fcntl
import hashlib
import json
import math
import os
import secrets
import sqlite3
import time
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass, fields
from datetime import UTC, datetime
from pathlib import Path

from .support import PolicyError, RateLimitError, encode, replace_text

ROOT = Path.home() / ".local/state/tg/clone"
VERSION = 1
PEER_CLASS = {
    "dialog": "user",
    "basic": "chat",
    "broadcast": "channel",
    "megagroup": "channel",
    "forum": "channel",
}
MAPS = ("id_map", "discussion_id_map", "topic_map", "avatar_photo_ids")
SCHEMA = """
CREATE TABLE clones (id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE mappings (
    clone TEXT REFERENCES clones(id) ON DELETE CASCADE,
    leg TEXT NOT NULL, source INTEGER NOT NULL CHECK(source > 0),
    dest INTEGER NOT NULL CHECK(dest > 0), PRIMARY KEY(clone, leg, source)
);
CREATE UNIQUE INDEX mapping_dest ON mappings(clone, leg, dest) WHERE leg != 'avatar_photo_ids';
CREATE TABLE pending (
    clone TEXT PRIMARY KEY REFERENCES clones(id) ON DELETE CASCADE, data TEXT NOT NULL
);
CREATE TABLE outcomes (
    clone TEXT REFERENCES clones(id) ON DELETE CASCADE, leg TEXT NOT NULL,
    source INTEGER NOT NULL, data TEXT NOT NULL, PRIMARY KEY(clone, leg, source)
);
CREATE TABLE events (id INTEGER PRIMARY KEY, clone TEXT, time REAL NOT NULL,
                     kind TEXT NOT NULL, data TEXT NOT NULL);
CREATE TABLE previews (id TEXT PRIMARY KEY, expires REAL NOT NULL, data TEXT NOT NULL);
CREATE TABLE cooldowns (account INTEGER PRIMARY KEY, deadline REAL NOT NULL);
CREATE TABLE votes (clone TEXT PRIMARY KEY REFERENCES clones(id) ON DELETE CASCADE,
                    data TEXT NOT NULL);
"""


def clone_id(account_user_id: int, source_peer_id: int, source_kind: str) -> str:
    identity = f"{account_user_id}:{PEER_CLASS[source_kind]}:{source_peer_id}"
    return hashlib.sha256(identity.encode()).hexdigest()


def valid_id(value, maximum=2_147_483_647):
    if type(value) is not int or not 0 < value <= maximum:
        raise PolicyError("invalid Telegram ID")
    return value


class SqlMap(Mapping):
    def __init__(self, clone, leg):
        self.clone, self.leg = clone, leg

    def __getitem__(self, key):
        try:
            key = int(key)
        except (ValueError, TypeError) as error:
            raise KeyError(key) from error
        row = self.clone.store.conn.execute(
            "SELECT dest FROM mappings WHERE clone=? AND leg=? AND source=?",
            (self.clone.clone_id, self.leg, key),
        ).fetchone()
        if row is None:
            raise KeyError(key)
        return row[0]

    def __iter__(self):
        return (key for key, _ in self.items())

    def __len__(self):
        return self.clone.store.conn.execute(
            "SELECT count(*) FROM mappings WHERE clone=? AND leg=?",
            (self.clone.clone_id, self.leg),
        ).fetchone()[0]

    def items(self):
        return (
            (str(source), dest)
            for source, dest in self.clone.store.conn.execute(
                "SELECT source, dest FROM mappings WHERE clone=? AND leg=? ORDER BY source",
                (self.clone.clone_id, self.leg),
            )
        )

    def values(self):
        return (dest for _, dest in self.items())


@dataclass
class CloneState:
    store: "Store"
    account_user_id: int
    source_peer_id: int
    source_title: str
    source_kind: str = "broadcast"
    destination_kind: str = "broadcast"
    destination_peer_id: int | None = None
    destination_title: str | None = None
    destination_username: str | None = None
    creation_marker: str | None = None
    cursor: int = 0
    created_at: str = ""
    last_synced_at: str | None = None
    discussion_source_peer_id: int | None = None
    discussion_destination_peer_id: int | None = None
    discussion_linked: bool = False
    discussion_cursor: int = 0
    comments: str = "none"
    pinned_dest_id: int | None = None
    pin_occupied: bool = False
    participants: dict | None = None
    progress: dict | None = None

    @property
    def clone_id(self):
        return clone_id(self.account_user_id, self.source_peer_id, self.source_kind)

    @property
    def id_map(self):
        return SqlMap(self, "id_map")

    @property
    def discussion_id_map(self):
        return SqlMap(self, "discussion_id_map")

    @property
    def topic_map(self):
        return SqlMap(self, "topic_map")

    @property
    def avatar_photo_ids(self):
        return SqlMap(self, "avatar_photo_ids")

    def record(self, leg, source_id, destination_id):
        if leg not in MAPS:
            raise PolicyError("unknown clone map")
        maximum = 2**63 - 1 if leg == "avatar_photo_ids" else 2_147_483_647
        valid_id(source_id, maximum)
        valid_id(destination_id, maximum)
        changed = self.store.conn.execute(
            "INSERT INTO mappings VALUES (?,?,?,?) ON CONFLICT(clone,leg,source) "
            "DO UPDATE SET dest=excluded.dest WHERE mappings.dest=excluded.dest "
            "OR excluded.leg='avatar_photo_ids'",
            (self.clone_id, leg, source_id, destination_id),
        )
        if not changed.rowcount:
            raise PolicyError("source message already maps to another destination")

    def record_mapping(self, source_id, destination_id):
        self.record("id_map", source_id, destination_id)

    def record_discussion_mapping(self, source_id, destination_id):
        self.record("discussion_id_map", source_id, destination_id)

    def record_topic(self, source_id, destination_id):
        if source_id < 2 or destination_id < 2:
            raise PolicyError("invalid forum topic mapping")
        self.record("topic_map", source_id, destination_id)

    def record_avatar(self, source_id, destination_id):
        self.record("avatar_photo_ids", source_id, destination_id)

    def dest_for(self, source_id):
        return self.id_map.get(str(source_id))

    def discussion_dest_for(self, source_id):
        return self.discussion_id_map.get(str(source_id))

    def topic_dest_for(self, source_id):
        return self.topic_map.get(str(source_id))

    def avatar_for(self, source_id):
        return self.avatar_photo_ids.get(str(source_id))

    def maximum(self, *maps):
        return self.store.conn.execute(
            "SELECT max(dest) FROM mappings WHERE clone=? "
            f"AND leg IN ({','.join('?' for _ in maps)})",
            (self.clone_id, *maps),
        ).fetchone()[0]

    def max_destination_id(self):
        return self.maximum("id_map", "topic_map")

    def max_discussion_destination_id(self):
        return self.maximum("discussion_id_map")

    def metadata(self):
        return {
            field.name: getattr(self, field.name) for field in fields(self) if field.name != "store"
        }

    def to_dict(self):
        return {
            "version": VERSION,
            **self.metadata(),
            **{name: dict(getattr(self, name).items()) for name in MAPS},
        }

    def artifact(self):
        outcomes = [
            {"leg": leg, "source_id": source, **json.loads(raw)}
            for leg, source, raw in self.store.conn.execute(
                "SELECT leg,source,data FROM outcomes WHERE clone=? ORDER BY leg,source",
                (self.clone_id,),
            )
        ]
        events = [
            {"time": time, "kind": kind, "data": json.loads(raw)}
            for time, kind, raw in self.store.conn.execute(
                "SELECT time,kind,data FROM events WHERE clone=? ORDER BY id", (self.clone_id,)
            )
        ]
        vote = self.store.conn.execute(
            "SELECT data FROM votes WHERE clone=?", (self.clone_id,)
        ).fetchone()
        return {
            **self.to_dict(),
            "outcomes": outcomes,
            "events": events,
            "pending": self.store.pending(self.clone_id),
            "pending_vote": json.loads(vote[0]) if vote else None,
        }

    def validate(self):
        for name in ("account_user_id", "source_peer_id"):
            valid_id(getattr(self, name), 2**63 - 1)
        for name in (
            "destination_peer_id",
            "discussion_source_peer_id",
            "discussion_destination_peer_id",
            "pinned_dest_id",
        ):
            value = getattr(self, name)
            if value is not None:
                valid_id(value, 2**63 - 1)
        for name in ("cursor", "discussion_cursor"):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= 2_147_483_647:
                raise PolicyError("invalid clone cursor")
        if (
            self.source_kind not in PEER_CLASS
            or not isinstance(self.source_title, str)
            or type(self.discussion_linked) is not bool
            or type(self.pin_occupied) is not bool
        ):
            raise PolicyError("invalid clone metadata")
        if self.comments == "enabled" and self.source_kind != "broadcast":
            raise PolicyError("only broadcasts have a discussion leg")
        if self.discussion_linked and not (
            self.discussion_source_peer_id and self.discussion_destination_peer_id
        ):
            raise PolicyError("linked discussion has missing peer IDs")

    def save(self):
        with self.store.conn:
            self.store.conn.execute(
                "INSERT INTO clones VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                (self.clone_id, encode(self.metadata())),
            )

    def event(self, kind, data):
        self.store.event(kind, data, self.clone_id)

    def outcome(self, leg, source_id, **data):
        self.store.conn.execute(
            "INSERT INTO outcomes VALUES (?,?,?,?) ON CONFLICT(clone,leg,source) "
            "DO UPDATE SET data=excluded.data",
            (self.clone_id, leg, source_id, encode(data)),
        )

    def prepare(self, leg, source_ids, signature, mode, issues):
        pending = self.store.pending(self.clone_id)
        identity = {"leg": leg, "source_ids": source_ids, "signature": signature}
        if pending:
            if any(pending[key] != value for key, value in identity.items()):
                raise PolicyError("unfinished send differs from source; inspect clone status")
            return pending["random_ids"]
        random_ids = [secrets.randbelow(2**63 - 1) + 1 for _ in source_ids]
        self.store.set_pending(
            self.clone_id, {**identity, "random_ids": random_ids, "mode": mode, "issues": issues}
        )
        return random_ids

    def confirm(self, destination_ids):
        pending = self.store.pending(self.clone_id)
        if pending is None or len(pending["source_ids"]) != len(destination_ids):
            raise PolicyError("incomplete clone receipt")
        if len(set(destination_ids)) != len(destination_ids):
            raise PolicyError("duplicate destination ID in clone receipt")
        for destination_id in destination_ids:
            valid_id(destination_id)
        self.store.set_pending(self.clone_id, {**pending, "destination_ids": destination_ids})

    def finish_pending(self):
        pending = self.store.pending(self.clone_id)
        if pending is None or "destination_ids" not in pending:
            return False
        with self.store.conn:
            for source_id, dest_id in zip(
                pending["source_ids"], pending["destination_ids"], strict=True
            ):
                self.record(pending["leg"], source_id, dest_id)
                self.outcome(
                    pending["leg"],
                    source_id,
                    status="degraded" if pending["issues"].get(str(source_id)) else "copied",
                    destination_id=dest_id,
                    mode=pending["mode"],
                    issues=pending["issues"].get(str(source_id), []),
                )
            if pending["leg"] == "id_map":
                self.cursor = pending["source_ids"][-1]
            elif pending["leg"] == "discussion_id_map":
                self.discussion_cursor = pending["source_ids"][-1]
            self.store.conn.execute("DELETE FROM pending WHERE clone=?", (self.clone_id,))
            self.save()
        return True


class Store:
    def __init__(self, root: Path | None = None, *, readonly=False):
        self.root = ROOT if root is None else Path(root)
        self.path = self.root / "state.sqlite3"
        self.readonly = readonly
        self.conn = None

    def __enter__(self):
        if self.readonly and not self.path.exists():
            return self
        if not self.readonly:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.root.chmod(0o700)
            descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
            os.close(descriptor)
            self.path.chmod(0o600)
        uri = f"{self.path.resolve().as_uri()}?mode={'ro' if self.readonly else 'rw'}"
        self.conn = sqlite3.connect(uri, uri=True)
        try:
            self.conn.execute("PRAGMA foreign_keys=ON")
            version = self.conn.execute("PRAGMA user_version").fetchone()[0]
            if version == 0 and not self.readonly:
                self._initialize()
            elif version != VERSION:
                raise PolicyError(f"unsupported clone state version: {version}")
            if self.conn.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise PolicyError("clone state failed integrity check")
            if not self.readonly:
                self.conn.execute("PRAGMA journal_mode=WAL")
                self.conn.execute("PRAGMA synchronous=FULL")
                self.conn.commit()
                for suffix in ("-wal", "-shm"):
                    sidecar = self.path.with_name(self.path.name + suffix)
                    if sidecar.exists():
                        sidecar.chmod(0o600)
        except (sqlite3.Error, PolicyError):
            self.conn.close()
            raise
        return self

    def _initialize(self):
        with self.conn:
            self.conn.execute("BEGIN IMMEDIATE")
            version = self.conn.execute("PRAGMA user_version").fetchone()[0]
            if version == VERSION:
                return
            if version != 0:
                raise PolicyError(f"unsupported clone state version: {version}")
            for statement in SCHEMA.split(";"):
                if statement.strip():
                    self.conn.execute(statement)
            self.conn.execute(f"PRAGMA user_version={VERSION}")

    def __exit__(self, *args):
        if self.conn:
            self.conn.close()

    @contextmanager
    def lock(self, account_id):
        valid_id(account_id, 2**63 - 1)
        with (self.root / f"{account_id}.lock").open("a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise PolicyError(
                    "another clone operation is using this Telegram account"
                ) from error
            yield

    def load(self, key):
        if self.conn is None:
            return None
        row = self.conn.execute("SELECT data FROM clones WHERE id=?", (key,)).fetchone()
        if row is None:
            return None
        try:
            result = CloneState(self, **json.loads(row[0]))
            result.validate()
            if result.clone_id != key or result.comments not in {
                "enabled",
                "disabled",
                "none",
                "unavailable",
            }:
                raise ValueError("invalid clone identity or comments")
            if result.destination_kind != (
                "forum" if result.source_kind == "forum" else "broadcast"
            ):
                raise ValueError("invalid destination kind")
        except (ValueError, TypeError, KeyError) as error:
            raise PolicyError("invalid clone state") from error
        return result

    def all(self):
        if self.conn is None:
            return []
        return [self.load(row[0]) for row in self.conn.execute("SELECT id FROM clones ORDER BY id")]

    def create(self, account_id, source_id, title, kind):
        if self.load(clone_id(account_id, source_id, kind)) is not None:
            raise PolicyError("clone already exists")
        result = CloneState(
            self,
            account_id,
            source_id,
            title,
            source_kind=kind,
            destination_kind="forum" if kind == "forum" else "broadcast",
            created_at=datetime.now(UTC).isoformat(),
        )
        result.validate()
        result.save()
        return result

    def preview(self, data):
        token, expiry = "p_" + secrets.token_urlsafe(24), time.time() + 300
        with self.conn:
            self.conn.execute("DELETE FROM previews WHERE expires<?", (time.time(),))
            self.conn.execute("INSERT INTO previews VALUES (?,?,?)", (token, expiry, encode(data)))
        return {"preview_id": token, "expires_at": datetime.fromtimestamp(expiry, UTC).isoformat()}

    def consume_preview(self, token, kind, account_id):
        with self.conn:
            row = self.conn.execute(
                "SELECT expires, data FROM previews WHERE id=?", (token,)
            ).fetchone()
            if row is None or row[0] <= time.time():
                raise PolicyError("clone preview is missing, expired or already used")
            payload = json.loads(row[1])
            if payload["account_user_id"] != account_id:
                raise PolicyError("preview belongs to a different Telegram account")
            if payload["kind"] != kind:
                raise PolicyError("clone preview has a different operation")
            self.conn.execute("DELETE FROM previews WHERE id=?", (token,))
        return payload

    def event(self, kind, data, clone=None):
        with self.conn:
            self.conn.execute(
                "INSERT INTO events(clone,time,kind,data) VALUES (?,?,?,?)",
                (clone, time.time(), kind, encode(data)),
            )

    def pending(self, key):
        row = self.conn.execute("SELECT data FROM pending WHERE clone=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def set_pending(self, key, data):
        with self.conn:
            self.conn.execute(
                "INSERT INTO pending VALUES (?,?) ON CONFLICT(clone) "
                "DO UPDATE SET data=excluded.data",
                (key, encode(data)),
            )

    def rejected(self, key, error):
        with self.conn:
            self.conn.execute("DELETE FROM pending WHERE clone=?", (key,))
            self.event("send-rejected", {"error": str(error)}, key)

    def cooldown(self, account_id, seconds=None):
        if seconds is not None:
            with self.conn:
                self.conn.execute(
                    "INSERT INTO cooldowns VALUES (?,?) ON CONFLICT(account) "
                    "DO UPDATE SET deadline=max(deadline,excluded.deadline)",
                    (account_id, time.time() + seconds),
                )
        row = self.conn.execute(
            "SELECT deadline FROM cooldowns WHERE account=?", (account_id,)
        ).fetchone()
        remaining = max(0, math.ceil(row[0] - time.time())) if row else 0
        if remaining:
            raise RateLimitError(remaining)

    def archive(self, clone):
        if self.conn.execute("SELECT 1 FROM votes WHERE clone=?", (clone.clone_id,)).fetchone():
            raise PolicyError("a pending poll vote must be retracted before replacing this clone")
        path = self.root / "archive" / f"{clone.clone_id}-{time.time_ns()}.json"
        replace_text(path, encode(clone.artifact()))
        with self.conn:
            self.conn.execute("DELETE FROM clones WHERE id=?", (clone.clone_id,))
            self.conn.execute("DELETE FROM events WHERE clone=?", (clone.clone_id,))
        return str(path)
