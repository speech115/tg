"""Classify replies once and choose their transport."""

from __future__ import annotations

from dataclasses import dataclass, replace

from telethon.tl import types

from . import attribution, batching, topics
from .support import PolicyError

_FLATTEN_FIELDS = ("todo_item_id", "poll_option")


@dataclass(frozen=True)
class Classification:
    kind: str
    parent_id: int | None = None
    top_id: int | None = None
    quote_text: str | None = None
    quote_entities: tuple = ()
    quote_offset: int | None = None
    peer: object | None = None


def _quote_fields(header) -> tuple[str | None, tuple, int | None]:
    return (header.quote_text, tuple(header.quote_entities or ()), header.quote_offset)


def _validate_parent_and_quote(header) -> None:
    parent_id, top_id = (header.reply_to_msg_id, header.reply_to_top_id)
    if parent_id is None or any(
        isinstance(item, bool) or not isinstance(item, int) or (not 0 < item <= 2147483647)
        for item in (parent_id, top_id)
        if item is not None
    ):
        raise PolicyError("clone reply parent is invalid")
    if (
        header.quote_text is not None
        and (not isinstance(header.quote_text, str))
        or (header.quote_entities and header.quote_text is None)
        or (
            header.quote_offset is not None
            and (
                header.quote_text is None
                or isinstance(header.quote_offset, bool)
                or (not isinstance(header.quote_offset, int))
                or (header.quote_offset < 0)
            )
        )
    ):
        raise PolicyError("clone reply quote is invalid")


def _peer_matches_id(peer, peer_id: int | None) -> bool:
    return isinstance(peer, types.PeerChannel) and peer.channel_id == peer_id


def _other_source_peer_id(leg) -> int | None:
    clone_state = leg.clone_state
    if leg.map_field == "discussion_id_map":
        return clone_state.source_peer_id
    return clone_state.discussion_source_peer_id


def _other_dest_for(leg, source_id: int) -> int | None:
    clone_state = leg.clone_state
    if leg.map_field == "discussion_id_map":
        return clone_state.dest_for(source_id)
    return clone_state.discussion_dest_for(source_id)


def _story_reply(header):
    if isinstance(header, types.MessageReplyStoryHeader):
        peer = header.peer
        peer_id = getattr(peer, "user_id", None) or getattr(peer, "channel_id", None)
        if (
            peer_id is None
            or isinstance(header.story_id, bool)
            or (not isinstance(header.story_id, int))
            or (header.story_id <= 0)
        ):
            raise PolicyError("clone Story reply shape is not supported")
        return True
    if not isinstance(header, types.MessageReplyHeader):
        raise PolicyError("clone reply shape is not supported")
    return False


def _classify_header(
    header, leg, source, *, posts_cursor: int | None = None, posts_exhausted: bool = False
) -> Classification | None:
    if header is None:
        return None
    if _story_reply(header):
        return Classification(kind="flatten")
    if (
        header.reply_to_scheduled
        or getattr(header, "reply_to_ephemeral", False)
        or any(getattr(header, field) is not None for field in _FLATTEN_FIELDS)
    ):
        return Classification(kind="flatten")
    _validate_parent_and_quote(header)
    forum = leg.destination_kind == "forum"
    parent_id = header.reply_to_msg_id
    assert isinstance(parent_id, int)
    top_id = header.reply_to_top_id
    quote_text, quote_entities, quote_offset = _quote_fields(header)
    peer = header.reply_to_peer_id

    def result(kind: str, *, clear_top: bool = False) -> Classification:
        return Classification(
            kind=kind,
            parent_id=parent_id,
            top_id=None if clear_top else top_id,
            quote_text=quote_text,
            quote_entities=quote_entities,
            quote_offset=quote_offset,
            peer=peer,
        )

    if peer is not None and (not attribution.same_peer(peer, source)):
        if _peer_matches_id(peer, _other_source_peer_id(leg)):
            if _other_dest_for(leg, parent_id) is not None:
                return result("mapped-cross-leg")
            if (
                leg.map_field == "discussion_id_map"
                and posts_cursor is not None
                and (parent_id > posts_cursor)
                and (not posts_exhausted)
            ):
                return result("deferred")
            return result("flatten")
        return result("foreign-peer")
    if header.forum_topic:
        if not forum or header.reply_to_top_id is None:
            return result("flatten")
        return (
            result("mapped-in-leg", clear_top=True)
            if leg.dest_for(parent_id) is not None
            else result("flatten", clear_top=True)
        )
    if leg.dest_for(parent_id) is not None:
        return result("mapped-in-leg")
    return result("flatten")


def target(
    messages, leg, source, *, posts_cursor: int | None = None, posts_exhausted: bool = False
) -> Classification | None:
    classifications = [
        _classify_header(
            getattr(message, "reply_to", None),
            leg,
            source,
            posts_cursor=posts_cursor,
            posts_exhausted=posts_exhausted,
        )
        for message in messages
    ]
    leading = classifications[0]
    if leading is None and any(item is not None for item in classifications[1:]):
        raise PolicyError("clone album reply appears after its leading item")
    if leading is not None and any(
        item is not None and item != leading for item in classifications[1:]
    ):
        raise PolicyError("clone album reply metadata is inconsistent")
    return leading


def input_reply(classified: Classification, leg) -> types.InputReplyToMessage | None:
    """Build the native reply input for a mapped-in-leg classification."""
    if classified.kind != "mapped-in-leg" or classified.parent_id is None:
        return None
    destination_id = leg.dest_for(classified.parent_id)
    if destination_id is None:
        return None
    top_destination_id = leg.dest_for(classified.top_id) if classified.top_id is not None else None
    return types.InputReplyToMessage(
        reply_to_msg_id=destination_id,
        top_msg_id=top_destination_id,
        quote_text=classified.quote_text,
        quote_entities=list(classified.quote_entities) or None,
        quote_offset=classified.quote_offset,
    )


@dataclass(frozen=True)
class TransportPlan:
    mode: str
    reply_to: object | None
    reply_flattened: bool
    needs_author: bool
    body_prefix: str | None = None
    body_prefix_entities: tuple = ()
    quote_flattened: dict | None = None
    classified: Classification | None = None


def as_reuploaded(plan: TransportPlan) -> TransportPlan:
    """Make a plan upload-capable while preserving snapshot transport."""
    return replace(
        plan,
        mode="snapshots" if plan.mode == "snapshots" else "reuploaded",
        needs_author=True,
        reply_flattened=False,
    )


def decide(
    messages, leg, source, *, posts_cursor: int | None = None, posts_exhausted: bool = False
) -> TransportPlan:
    classified = target(
        messages, leg, source, posts_cursor=posts_cursor, posts_exhausted=posts_exhausted
    )
    header = getattr(messages[0], "reply_to", None)
    if classified is None:
        reply_to = None
        reply_flattened = False
    elif classified.kind == "deferred":
        return TransportPlan(
            mode="deferred",
            reply_to=None,
            reply_flattened=False,
            needs_author=False,
            classified=classified,
        )
    elif classified.kind == "mapped-in-leg":
        reply_to = input_reply(classified, leg)
        reply_flattened = False
    elif classified.kind == "flatten":
        reply_to = None
        reply_flattened = not (leg.destination_kind == "forum" and topics.placement_only(header))
    else:
        reply_to = None
        reply_flattened = True
    if len(messages) == 1 and batching.supports(messages[0]):
        mode = "snapshots"
    elif (
        getattr(source, "noforwards", False)
        or reply_to is not None
        or any(getattr(message, "noforwards", False) for message in messages)
    ):
        mode = "reuploaded"
    else:
        mode = "forwarded"
    needs_author = mode != "forwarded" and (
        leg.source_kind != "broadcast" or getattr(messages[0], "fwd_from", None) is not None
    )
    return TransportPlan(
        mode=mode,
        reply_to=reply_to,
        reply_flattened=reply_flattened,
        needs_author=needs_author,
        classified=classified,
    )
