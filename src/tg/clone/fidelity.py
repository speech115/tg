"""Classify supported media and report controls that cannot be copied."""

from telethon.tl import types

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
