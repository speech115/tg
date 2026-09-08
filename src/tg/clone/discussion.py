"""Private discussion groups, linking, anchors and destination tail checks."""

from typing import cast

from telethon import errors as telethon_errors
from telethon.tl import functions, types

from . import batching, topics
from .support import PolicyError

PEER_UNAVAILABLE = (
    ValueError,
    telethon_errors.ChannelPrivateError,
    telethon_errors.ChannelInvalidError,
    telethon_errors.ChatForbiddenError,
)


def linked_chat_id(full_channel) -> int | None:
    """ChannelFull.linked_chat_id only. linked_monoforum_id is a monoforum, not a comment
    section (live-proven on @groks) — never read it."""
    chat_id = getattr(full_channel, "linked_chat_id", None)
    if type(chat_id) is not int or chat_id <= 0:
        return None
    return chat_id


def is_discussion_destination(entity, *, title: str | None = None) -> bool:
    """Private owned megagroup that is not a forum."""
    return topics.is_forum_destination(entity, title=title) and (
        not getattr(entity, "forum", False)
    )


def autoforward_post_id(message, source_channel_id: int) -> int | None:
    """Source post id if message is Telegram's auto-forward anchor for source_channel_id,
    else None. Matches fwd_from.saved_from_peer + saved_from_msg_id (live-proven)."""
    header = getattr(message, "fwd_from", None)
    if not isinstance(header, types.MessageFwdHeader):
        return None
    peer = header.saved_from_peer
    if not isinstance(peer, types.PeerChannel) or peer.channel_id != source_channel_id:
        return None
    post_id = header.saved_from_msg_id
    if type(post_id) is not int or not 0 < post_id <= 2147483647:
        return None
    return post_id


async def verify_tail(tg, destination, recorded_last_id, label, expected) -> None:
    """Tail guard shared by both clone legs: nothing may sit past the recorded tail unless
    `expected` vouches for it (service messages on the channel, Telegram's own auto-
    forwards in the discussion group)."""
    latest = await tg.get_messages(destination, limit=1)
    destination_last_id = latest[0].id if latest else 0
    if recorded_last_id is not None and recorded_last_id > destination_last_id:
        raise PolicyError(f"clone {label} recorded tail is missing; manual repair is required")
    baseline = recorded_last_id or 1
    if destination_last_id <= baseline:
        return
    tail = await tg.get_messages(destination, limit=destination_last_id - baseline)
    unexpected = [item for item in tail if item.id > baseline and (not expected(item))]
    if unexpected:
        raise PolicyError(
            f"clone {label} has unexpected tail messages; manual repair is required",
            unexpected=len(unexpected),
        )


async def adopt(tg, marker_candidates, marker, recorded_peer_id, on_create):
    """The recorded peer, else the single marker-matched group, else a fresh one. Same
    marker discipline as the destination channel."""
    if recorded_peer_id is not None:
        try:
            return await tg.get_entity(types.PeerChannel(recorded_peer_id))
        except PEER_UNAVAILABLE:
            raise PolicyError("clone discussion group is unavailable") from None
    valid, wrong_shape = await marker_candidates(marker, is_discussion_destination)
    if len(valid) + len(wrong_shape) > 1:
        raise PolicyError("clone discussion marker matched multiple groups")
    if wrong_shape:
        raise PolicyError("clone discussion marker matched a group with wrong shape")
    if valid:
        return valid[0]
    on_create()
    update = await tg(topics.create_request(marker))
    candidates = [
        item
        for item in getattr(update, "chats", ())
        if is_discussion_destination(item, title=marker)
    ]
    if len(candidates) != 1:
        raise PolicyError("Telegram did not return the created discussion group")
    return candidates[0]


async def ensure_linked(tg, channel, group) -> None:
    """Idempotent: unhide pre-history, then SetDiscussionGroupRequest. Telegram answers a
    no-op with an error rather than silence, and both no-ops are the normal path (live-
    proven): a megagroup it just created already shows its history, and crash recovery
    re-links an already-linked pair."""
    for request, benign in (
        (
            functions.channels.TogglePreHistoryHiddenRequest(channel=group, enabled=False),
            telethon_errors.ChatNotModifiedError,
        ),
        (
            functions.channels.SetDiscussionGroupRequest(broadcast=channel, group=group),
            telethon_errors.LinkNotModifiedError,
        ),
    ):
        try:
            await tg(request)
        except benign:
            pass


async def anchor_for(tg, destination_channel, destination_post_id: int, cache: dict) -> int | None:
    """Destination anchor message id in the discussion group, via
    messages.getDiscussionMessage. Cached per run; None when Telegram returns no anchor."""
    if destination_post_id in cache:
        return cache[destination_post_id]
    response = await tg(
        functions.messages.GetDiscussionMessageRequest(
            peer=destination_channel, msg_id=destination_post_id
        )
    )
    # Albums arrive in reverse order; only the leading post accepts this RPC.
    # Cache every member by its source post so replies can target individual photos.
    for item in getattr(response, "messages", None) or ():
        post_id = autoforward_post_id(item, destination_channel.id)
        if post_id is not None and type(item.id) is int and 0 < item.id <= 2147483647:
            cache[post_id] = item.id
    return cache.setdefault(destination_post_id, None)


def anchor_posts(messages, source_channel_id) -> dict[int, int] | None:
    """Anchor id -> source post id for a batch of Telegram's own auto-forwards, or None when
    the batch is real content. A channel album auto-forwards as an album, so an anchor
    batch can carry several messages."""
    found = {message.id: autoforward_post_id(message, source_channel_id) for message in messages}
    if all(post_id is None for post_id in found.values()):
        return None
    if any(post_id is None for post_id in found.values()):
        raise PolicyError("clone discussion anchor album is incomplete")
    return cast(dict[int, int], found)


ACCESS_ERRORS = (*PEER_UNAVAILABLE, telethon_errors.ChatAdminRequiredError)


def _degrade(clone_state):
    clone_state.event("comments-unavailable", {"cursor": clone_state.discussion_cursor})
    clone_state.comments = "unavailable"
    clone_state.save()


async def _destination_group(tg, clone_state, resolve_ctx):
    group = getattr(resolve_ctx, "destination_group", None)
    if group is None:
        try:
            group = await tg.get_entity(
                types.PeerChannel(clone_state.discussion_destination_peer_id)
            )
        except PEER_UNAVAILABLE:
            raise PolicyError("clone discussion destination is unavailable") from None
        if not is_discussion_destination(group):
            raise PolicyError("clone discussion destination is not a private owned megagroup")
        resolve_ctx.destination_group = group
    return group


async def comment_events(tg, clone, source_channel, destination, ctx):
    """Yield discussion batches; preserve cursors if source access disappears.

    Scheduling, limits and sending belong to Sync, not callbacks inside this reader.
    A send error in the consumer must never be mistaken for lost read access.
    """
    source_group = ctx.source_group
    if source_group is None:
        try:
            source_group = await tg.get_entity(types.PeerChannel(clone.discussion_source_peer_id))
        except ACCESS_ERRORS:
            _degrade(clone)
            return
    group = await _destination_group(tg, clone, ctx)
    await verify_tail(
        tg,
        group,
        clone.max_discussion_destination_id(),
        "discussion destination",
        lambda item: (
            getattr(item, "action", None) is not None
            or autoforward_post_id(item, destination.id) is not None
        ),
    )
    ctx.source_group, ctx.source_channel_id, ctx.destination = (
        source_group,
        source_channel.id,
        destination,
    )
    events = aiter(
        batching.plan(tg.iter_messages(source_group, min_id=clone.discussion_cursor, reverse=True))
    )
    while True:
        try:
            event = await anext(events)
        except StopAsyncIteration:
            return
        except telethon_errors.FloodWaitError:
            raise
        except ACCESS_ERRORS:
            _degrade(clone)
            return
        yield event
