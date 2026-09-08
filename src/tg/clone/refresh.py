"""Preview and apply missing attribution prefixes to untouched destination bodies."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import batched

from . import attribution, fidelity, quote_fallback, transport


def _entities_equal(left, right) -> bool:
    left_list = list(left or ())
    right_list = list(right or ())
    if len(left_list) != len(right_list):
        return False
    return all((a.to_dict() == b.to_dict() for a, b in zip(left_list, right_list)))


def eligible_for_backfill(
    message, dest_text, dest_entities, rendered_text, rendered_entities
) -> bool:
    """True only when dest is the unprefixed source body and a prefix is due."""
    source_text = getattr(message, "message", None) or ""
    source_entities = getattr(message, "entities", None)
    if (dest_text or "") != source_text:
        return False
    if not _entities_equal(dest_entities, source_entities):
        return False
    if (rendered_text or "") == source_text and _entities_equal(rendered_entities, source_entities):
        return False
    return True


async def render_with_current_rules(tg, source, message, me, source_kind: str, cache: dict):
    """Reuse sync's body renderer: source_kind-branched attribution + apply_body."""
    author = None
    if source_kind == "broadcast":
        if getattr(message, "fwd_from", None) is not None:
            author = await attribution.forwarded_author_of(tg, message, cache)
    else:
        author = await attribution.author_of(tg, source, message, me, cache)
    plan = transport.TransportPlan(
        mode="reuploaded", reply_to=None, reply_flattened=False, needs_author=True
    )
    return quote_fallback.apply_body(message, author, plan)


@dataclass(frozen=True)
class Candidate:
    source_id: int
    destination_id: int


@dataclass(frozen=True)
class Excluded:
    source_id: int
    reason: str


def _exclusion(message, destination, previous, first):
    if message is None or destination is None:
        return "missing"
    if message.fwd_from is None:
        return "not-forwarded"
    if fidelity.supports(message):
        return "poll-snapshot"
    if destination.fwd_from is not None:
        return "native-reforward"
    if message.grouped_id is not None and (not first):
        if previous is None:
            return "album-lead-unknown"
        if previous.grouped_id == message.grouped_id:
            return "album-non-lead"
    return None


async def candidates(tg, clone_state, source_entity, destination_entity, me):
    """Read histories in bounded chunks, retaining one neighbor for album lead detection."""
    eligible, excluded, author_cache = ([], [], {})
    previous, first = (None, True)
    for chunk in batched(clone_state.id_map.items(), 100):
        source_ids, dest_ids = zip(*chunk, strict=True)
        source_ids = [int(value) for value in source_ids]
        source_msgs = await tg.get_messages(source_entity, ids=source_ids)
        dest_msgs = await tg.get_messages(destination_entity, ids=list(dest_ids))
        for source_id, dest_id, message, destination in zip(
            source_ids, dest_ids, source_msgs, dest_msgs, strict=True
        ):
            reason = _exclusion(message, destination, previous, first)
            previous, first = (message, False)
            if reason:
                excluded.append(Excluded(source_id, reason))
                continue
            text, entities = await render_with_current_rules(
                tg, source_entity, message, me, clone_state.source_kind, author_cache
            )
            if eligible_for_backfill(
                message, destination.message, destination.entities, text, entities
            ):
                eligible.append(Candidate(source_id, dest_id))
            else:
                excluded.append(Excluded(source_id, "not-eligible"))
    return (eligible, excluded)
