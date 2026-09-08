"""Plan complete albums, service skips and content eligibility."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from telethon.tl import types

from .support import PolicyError


@dataclass(frozen=True)
class ServiceSkip:
    message_id: int
    message: Any


@dataclass(frozen=True)
class Batch:
    messages: tuple


def _group_id(message):
    grouped_id = getattr(message, "grouped_id", None)
    if grouped_id is None:
        return None
    if isinstance(grouped_id, bool) or not isinstance(grouped_id, int):
        raise PolicyError("clone album group id is invalid")
    return grouped_id


async def plan(messages):
    """Yield ServiceSkip and Batch events from an async message stream."""
    album: list = []
    async for message in messages:
        if getattr(message, "action", None) is not None:
            if album:
                yield Batch(tuple(album))
                album = []
            yield ServiceSkip(message.id, message)
            continue
        grouped_id = _group_id(message)
        if grouped_id is not None:
            if album and album[0].grouped_id == grouped_id:
                album.append(message)
                continue
            if album:
                yield Batch(tuple(album))
            album = [message]
            continue
        if album:
            yield Batch(tuple(album))
            album = []
        yield Batch((message,))
    if album:
        yield Batch(tuple(album))


_NATIVE_MEDIA_TYPES = (
    types.MessageMediaWebPage,
    types.MessageMediaPhoto,
    types.MessageMediaDocument,
)


def supports(message) -> bool:
    return isinstance(
        getattr(message, "media", None), (types.MessageMediaPoll, types.MessageMediaStory)
    )


def dropped_buttons(message) -> list[dict] | None:
    """The message's keyboard buttons, or None when it carries no keyboard."""
    rows = getattr(getattr(message, "reply_markup", None), "rows", None) or ()
    buttons = [
        {"type": type(button).__name__, "text": getattr(button, "text", None)}
        for row in rows
        for button in getattr(row, "buttons", None) or ()
    ]
    return buttons or None


def unsupported_kind(message) -> str | None:
    media = getattr(message, "media", None)
    if getattr(media, "ttl_seconds", None) is not None:
        return f"{type(media).__name__}TTL"
    return (
        None
        if media is None or isinstance(media, _NATIVE_MEDIA_TYPES) or supports(message)
        else type(media).__name__
    )
