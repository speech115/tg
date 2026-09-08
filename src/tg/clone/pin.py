"""Copy the first mappable source pin without overwriting an existing destination pin."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from telethon.tl import functions, types


@dataclass(frozen=True)
class PinState:
    pinned_dest_id: int | None = None
    pin_occupied: bool = False


@dataclass(frozen=True)
class PinDecision:
    status: str
    destination_id: int | None


def decide(
    source_pinned_msg_id: int | None, id_map: dict[str, int], pin_state: PinState
) -> PinDecision:
    """Pure intent: whether this clone should pin, and which destination id."""
    if pin_state.pin_occupied:
        return PinDecision(status="occupied", destination_id=None)
    if pin_state.pinned_dest_id is not None:
        return PinDecision(status="unchanged", destination_id=pin_state.pinned_dest_id)
    if source_pinned_msg_id is None:
        return PinDecision(status="unmapped", destination_id=None)
    mapped = id_map.get(str(source_pinned_msg_id))
    if mapped is None:
        return PinDecision(status="unmapped", destination_id=None)
    return PinDecision(status="set", destination_id=mapped)


def snapshot(clone_state) -> dict[str, Any]:
    """Report pin status from state alone — no live check this run."""
    if clone_state.pinned_dest_id is not None:
        return {"source_id": None, "destination_id": clone_state.pinned_dest_id, "status": "set"}
    if clone_state.pin_occupied:
        return {"source_id": None, "destination_id": None, "status": "occupied"}
    return {"source_id": None, "destination_id": None, "status": "unmapped"}


def _pin_state_of(clone_state) -> PinState:
    return PinState(
        pinned_dest_id=clone_state.pinned_dest_id, pin_occupied=clone_state.pin_occupied
    )


async def _source_pinned_msg_id(tg, source) -> int | None:
    """Read the source's current pinned_msg_id via the matching GetFull* RPC."""
    if isinstance(source, types.User):
        full = await tg(functions.users.GetFullUserRequest(source))
        return getattr(full.full_user, "pinned_msg_id", None)
    if isinstance(source, types.Chat):
        full = await tg(functions.messages.GetFullChatRequest(chat_id=source.id))
        return getattr(full.full_chat, "pinned_msg_id", None)
    full = await tg(functions.channels.GetFullChannelRequest(source))
    return getattr(full.full_chat, "pinned_msg_id", None)


async def sync_phase(tg, clone_state, source_entity, destination) -> dict[str, Any]:
    """Carry the source pin onto a broadcast destination when first mappable."""
    existing = _pin_state_of(clone_state)
    if existing.pin_occupied or existing.pinned_dest_id is not None:
        decision = decide(None, clone_state.id_map, existing)
        return {
            "source_id": None,
            "destination_id": decision.destination_id,
            "status": decision.status,
        }
    source_pinned = await _source_pinned_msg_id(tg, source_entity)
    decision = decide(source_pinned, clone_state.id_map, existing)
    if decision.status != "set":
        return {"source_id": source_pinned, "destination_id": None, "status": "unmapped"}
    dest_full = await tg(functions.channels.GetFullChannelRequest(destination))
    dest_pinned = getattr(dest_full.full_chat, "pinned_msg_id", None)
    if dest_pinned == decision.destination_id:
        clone_state.pinned_dest_id = decision.destination_id
        clone_state.save()
        return {
            "source_id": source_pinned,
            "destination_id": decision.destination_id,
            "status": "unchanged",
        }
    if dest_pinned is not None:
        clone_state.pin_occupied = True
        clone_state.save()
        return {"source_id": source_pinned, "destination_id": None, "status": "occupied"}
    clone_state.event(
        "clone-sync-pin",
        {
            "clone_id": clone_state.clone_id,
            "source_message_id": source_pinned,
            "destination_message_id": decision.destination_id,
        },
    )
    assert decision.destination_id is not None
    dest_peer = await tg.get_input_entity(destination)
    await tg(
        functions.messages.UpdatePinnedMessageRequest(
            peer=dest_peer, id=decision.destination_id, silent=True
        )
    )
    clone_state.pinned_dest_id = decision.destination_id
    clone_state.save()
    return {"source_id": source_pinned, "destination_id": decision.destination_id, "status": "set"}
