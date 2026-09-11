"""Report phase and byte progress to stderr and local clone state."""

from __future__ import annotations

import os
import time
from collections.abc import Callable

from telethon import errors as telethon_errors

from .support import note, sanitize

MEGABYTE = 1024 * 1024
PROGRESS_EVERY_BYTES = 5 * MEGABYTE


async def approximate_total(tg, entity) -> int | None:
    """Best-effort source size for the `~total`; never fails a sync."""
    try:
        return (await tg.get_messages(entity, limit=0)).total
    except telethon_errors.FloodWaitError:
        raise
    except (telethon_errors.RPCError, AttributeError, ValueError):
        return None


def transfer_of(progress, message, direction: str):
    """None-safe transfer callback, so the reupload legs stay unconditional."""
    if progress is None:
        return None
    return progress.transfer(media_label(message), direction)


def media_label(message) -> str:
    """Best-effort human name for the file a reupload is moving."""
    name = getattr(getattr(message, "file", None), "name", None)
    if isinstance(name, str) and name:
        return name
    return f"message-{getattr(message, 'id', '?')}"


class SyncProgress:
    """Counts copied messages and renders the sync's current activity."""

    def __init__(
        self,
        source_id: int,
        *,
        clone=None,
        total: int | None = None,
        copied: int = 0,
        write: Callable[[str], None] = note,
    ) -> None:
        self.clone = clone
        self._source_id = source_id
        self._total = total
        self._copied = copied
        self._write = write
        self._total_resolved = total is not None
        self._known: dict[int, int | None] = {}

    def persist(self, **data):
        if self.clone is not None:
            self.clone.progress = {
                **(self.clone.progress or {}),
                "status": "running",
                "pid": os.getpid(),
                "updated_at": time.time(),
                "copied": self._copied,
                "total": self._total,
                **data,
            }
            self.clone.save()

    async def resolve_total(self, tg, entity) -> None:
        """Fetch `~total` once per entity, lazily, on the first batch reported."""
        if self._total_resolved:
            return
        self._total_resolved = True
        marker = getattr(entity, "id", None)
        key = marker if type(marker) is int else id(entity)
        if key not in self._known:
            self._known[key] = await approximate_total(tg, entity)
        self._total = self._known[key]

    def _prefix(self) -> str:
        total = "?" if self._total is None else self._total
        return f"[sync {self._source_id}] {self._copied}/~{total}"

    def batch(self, count: int, transport: str) -> None:
        """Report a finished batch and the transport it went out through."""
        self._copied += count
        self.persist(transport=transport, file=None, bytes=None)
        self._write(f"{self._prefix()} · {transport}")

    def phase(self, name: str, *, copied: int = 0) -> None:
        """Start a new leg: announce it, and restart both counters for it."""
        self._copied = copied
        self._total = None
        self._total_resolved = False
        self.persist(phase=name, file=None, bytes=None)
        self._write(f"{self._prefix()} · {name}")

    def transfer(self, filename: str, direction: str) -> Callable[..., None]:
        """Return a byte-progress callback throttled to one line per ~5 MB."""
        filename = sanitize(filename)
        self.persist(file=filename, direction=direction, bytes=0, file_size=None)
        reported = 0

        def report(current: int, total: int | None) -> None:
            nonlocal reported
            complete = isinstance(total, int) and total > 0 and (current >= total)
            if not complete and current - reported < PROGRESS_EVERY_BYTES:
                return
            reported = current
            self.persist(file=filename, direction=direction, bytes=current, file_size=total)
            done = f"{current / MEGABYTE:.1f}"
            if isinstance(total, int) and total > 0:
                percent = int(current * 100 / total)
                measure = f"{done}/{total / MEGABYTE:.1f} MB ({percent}%)"
            else:
                measure = f"{done} MB"
            self._write(f"{self._prefix()} · reupload · {filename} · {direction} {measure}")

        return report
