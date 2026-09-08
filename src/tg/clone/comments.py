"""Copy discussion messages while remapping channel-post anchors."""

from typing import cast

from telethon import errors as telethon_errors
from telethon.tl import types

from . import batching, discussion, legs, replies
from .support import PolicyError


def _anchor_posts(messages, source_channel_id) -> dict[int, int] | None:
    """Anchor id -> source post id for a batch of Telegram's own auto-forwards, or None when
    the batch is real content. A channel album auto-forwards as an album, so an anchor
    batch can carry several messages."""
    found = {
        message.id: discussion.autoforward_post_id(message, source_channel_id)
        for message in messages
    }
    if all(post_id is None for post_id in found.values()):
        return None
    if any(post_id is None for post_id in found.values()):
        raise PolicyError("clone discussion anchor album is incomplete")
    return cast(dict[int, int], found)


ACCESS_ERRORS = (*discussion.PEER_UNAVAILABLE, telethon_errors.ChatAdminRequiredError)


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
        except discussion.PEER_UNAVAILABLE:
            raise PolicyError("clone discussion destination is unavailable") from None
        if not discussion.is_discussion_destination(group):
            raise PolicyError("clone discussion destination is not a private owned megagroup")
        resolve_ctx.destination_group = group
    return group


async def sync_phase(
    tg,
    clone_state,
    source_channel,
    destination,
    copy_batch,
    counters,
    limited,
    resolve_ctx,
    *,
    posts_exhausted: bool = False,
) -> bool:
    """Copy the source discussion group into the clone's. Parent posts that this phase needs
    must already be mapped, or a cross-leg comment whose parent sits beyond the posts
    cursor defers instead of flattening — unless the posts leg is already exhausted, in
    which case that parent is permanently gone and flattens. Returns True when the
    --limit stop landed inside this phase."""
    leg = legs.discussion(clone_state)
    source_group = getattr(resolve_ctx, "source_group", None)
    if source_group is None:
        try:
            source_group = await tg.get_entity(
                types.PeerChannel(clone_state.discussion_source_peer_id)
            )
        except ACCESS_ERRORS:
            _degrade(clone_state)
            return False
    group = await _destination_group(tg, clone_state, resolve_ctx)
    await discussion.verify_tail(
        tg,
        group,
        clone_state.max_discussion_destination_id(),
        "discussion destination",
        lambda item: (
            getattr(item, "action", None) is not None
            or discussion.autoforward_post_id(item, destination.id) is not None
        ),
    )
    resolve_ctx.source_group = source_group
    resolve_ctx.source_channel_id = source_channel.id
    resolve_ctx.destination = destination
    events = aiter(batching.plan(tg.iter_messages(source_group, min_id=leg.cursor, reverse=True)))
    while True:
        try:
            event = await anext(events)
        except StopAsyncIteration:
            break
        except telethon_errors.FloodWaitError:
            raise
        except ACCESS_ERRORS:
            _degrade(clone_state)
            return False
        if limited():
            return True
        if isinstance(event, batching.ServiceSkip):
            counters["skipped_service"] += 1
            leg.cursor = event.message_id
        elif (posts := _anchor_posts(event.messages, source_channel.id)) is not None:
            if not posts_exhausted and any(
                post_id > clone_state.cursor for post_id in posts.values()
            ):
                return False
            resolve_ctx.anchors.update(posts)
            counters["skipped_autoforward"] += len(posts)
            leg.cursor = event.messages[-1].id
        else:
            classified = replies.target(
                event.messages,
                leg,
                source_group,
                posts_cursor=clone_state.cursor,
                posts_exhausted=posts_exhausted,
            )
            if classified is not None and classified.kind == "deferred":
                return False
            await copy_batch(event.messages, leg, source_group, group)
            continue
        clone_state.save()
    return False
