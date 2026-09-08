"""Forward a protected repost from its accessible original only when content matches."""

from datetime import timedelta

from telethon import errors as telethon_errors
from telethon.tl import types

SEARCH_LIMIT = 20
_GROUP_KEY = "source-group"


def eligible(leg, messages, plan) -> bool:
    """Whether a batch may spend a search on proving its original."""
    if plan.mode != "reuploaded" or leg.source_kind != "broadcast":
        return False
    if len(messages) != 1 or plan.reply_to is not None:
        return False
    if plan.body_prefix or plan.quote_flattened is not None:
        return False
    return _searchable(getattr(messages[0], "fwd_from", None)) is not None


async def locate(tg, clone_state, message, cache: dict):
    """``(group, message_id)`` to forward natively, or None to keep the prefix."""
    searchable = _searchable(getattr(message, "fwd_from", None))
    if searchable is None:
        return None
    peer, date = searchable
    group = await source_group(tg, clone_state, cache)
    if group is None:
        return None
    found = await _guarded(
        lambda: tg.get_messages(
            group, from_user=peer, offset_date=date + timedelta(seconds=1), limit=SEARCH_LIMIT
        )
    )
    dated = [item for item in found or () if getattr(item, "date", None) == date]
    if len(dated) != 1:
        return None
    candidate = dated[0]
    if not _same_content(message, candidate):
        return None
    return (group, candidate.id)


async def source_group(tg, clone_state, cache: dict):
    """The source discussion group entity, resolved once per sync run."""
    if _GROUP_KEY in cache:
        return cache[_GROUP_KEY]
    peer_id = getattr(clone_state, "discussion_source_peer_id", None)
    group = None
    if peer_id is not None:
        group = await _guarded(lambda: tg.get_entity(types.PeerChannel(peer_id)))
        if group is not None and getattr(group, "noforwards", False):
            group = None
    cache[_GROUP_KEY] = group
    return group


def _searchable(fwd):
    """``(peer, date)`` when `fwd_from` names a peer and a moment to search by."""
    peer = getattr(fwd, "from_id", None)
    date = getattr(fwd, "date", None)
    if not isinstance(peer, (types.PeerUser, types.PeerChannel)) or date is None:
        return None
    return (peer, date)


def _same_content(post, candidate) -> bool:
    """Text, formatting, keyboard and media identical."""
    if (getattr(post, "message", "") or "") != (getattr(candidate, "message", "") or ""):
        return False
    if _entities_key(post) != _entities_key(candidate):
        return False
    if _markup_key(post) != _markup_key(candidate):
        return False
    return _media_key(post) == _media_key(candidate)


def _tl_key(item):
    """Everything Telegram sent for ``item``, not a chosen list of fields."""
    to_dict = getattr(item, "to_dict", None)
    return to_dict() if callable(to_dict) else object()


def _entities_key(message):
    return tuple(_tl_key(item) for item in getattr(message, "entities", None) or ())


def _markup_key(message):
    """The keyboard as content (#183)."""
    markup = getattr(message, "reply_markup", None)
    return None if markup is None else _tl_key(markup)


def _media_key(message):
    """Identity *and* presentation of the attached media."""
    media = getattr(message, "media", None)
    if media is None:
        return None
    spoiler = bool(getattr(media, "spoiler", False))
    for attribute in ("photo", "document", "webpage"):
        carried = getattr(media, attribute, None)
        if carried is not None:
            return (type(media).__name__, attribute, getattr(carried, "id", None), spoiler)
    return (type(media).__name__, None, None, spoiler)


async def _guarded(make_awaitable):
    """Treat an inaccessible original as absent; propagate rate limits."""
    try:
        return await make_awaitable()
    except telethon_errors.FloodWaitError:
        raise
    except (ValueError, telethon_errors.RPCError):
        return None
