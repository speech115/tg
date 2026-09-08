"""Create private clone peers and copy their profiles."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from telethon import errors as telethon_errors
from telethon.tl import functions, types

from . import attribution, discussion
from .support import PolicyError


def is_private_owned_broadcast(entity, *, title: str | None = None) -> bool:
    active = any(
        getattr(item, "active", False) for item in getattr(entity, "usernames", None) or ()
    )
    return bool(
        (title is None or getattr(entity, "title", None) == title)
        and getattr(entity, "creator", False)
        and getattr(entity, "broadcast", False)
        and (not getattr(entity, "megagroup", False))
        and (getattr(entity, "username", None) is None)
        and (not active)
    )


async def marker_candidates(tg, marker: str, shape_ok) -> tuple[list[Any], list[Any]]:
    valid = []
    wrong_shape = []
    async for dialog in tg.iter_dialogs():
        entity = getattr(dialog, "entity", None)
        if getattr(entity, "title", None) != marker:
            continue
        (valid if shape_ok(entity, title=marker) else wrong_shape).append(entity)
    return (valid, wrong_shape)


async def copy_profile(tg, source, destination, clone_state):
    """Copies about/avatar onto destination; returns the source's full chat."""
    clone_id = clone_state.clone_id
    if isinstance(source, types.User):
        full = await tg(functions.users.GetFullUserRequest(source))
        about = getattr(full.full_user, "about", None) or ""
    elif isinstance(source, types.Chat):
        full = await tg(functions.messages.GetFullChatRequest(chat_id=source.id))
        about = getattr(full.full_chat, "about", None) or ""
    else:
        full = await tg(functions.channels.GetFullChannelRequest(source))
        about = getattr(full.full_chat, "about", None) or ""
    if about:
        clone_state.event("clone-init-about", {"clone_id": clone_id, "source_peer_id": source.id})
        try:
            await tg(functions.messages.EditChatAboutRequest(peer=destination, about=about))
        except telethon_errors.ChatAboutNotModifiedError:
            pass
    full_chat = getattr(full, "full_chat", None)
    photo = getattr(source, "photo", None)
    if photo is None or isinstance(photo, (types.ChatPhotoEmpty, types.UserProfilePhotoEmpty)):
        return full_chat
    photo_id = getattr(photo, "photo_id", None)
    if photo_id is not None and clone_state.avatar_for(source.id) == photo_id:
        return full_chat
    with tempfile.TemporaryDirectory(prefix="avatar-", dir=clone_state.store.root) as workdir:
        downloaded = await tg.download_profile_photo(source, file=Path(workdir) / "avatar")
        if downloaded is None:
            raise PolicyError("clone source avatar download failed")
        uploaded = await tg.upload_file(downloaded)
        clone_state.event("clone-init-avatar", {"clone_id": clone_id, "source_peer_id": source.id})
        await tg(
            functions.channels.EditPhotoRequest(
                channel=destination, photo=types.InputChatUploadedPhoto(file=uploaded)
            )
        )
        if photo_id is not None:
            clone_state.record_avatar(source.id, photo_id)
            clone_state.save()
    return full_chat


async def init_discussion(tg, destination, clone_state, full_chat, clone_id) -> None:
    """Create/adopt and link the destination discussion group before any post. An unreadable
    source group is not an error: the clone stays posts-only and honestly records
    comments == "unavailable"."""
    if clone_state.source_kind != "broadcast":
        return
    linked = discussion.linked_chat_id(full_chat)
    if linked is None:
        clone_state.comments = "none"
        return clone_state.save()
    if clone_state.discussion_source_peer_id not in (None, linked):
        raise PolicyError("source discussion group changed; use init --replace")
    clone_state.discussion_source_peer_id = linked
    try:
        source_group = await tg.get_entity(types.PeerChannel(linked))
        await tg.get_messages(source_group, limit=1)
    except (
        ValueError,
        telethon_errors.ChannelPrivateError,
        telethon_errors.ChatAdminRequiredError,
    ):
        clone_state.comments = "unavailable"
        return clone_state.save()
    clone_state.comments = "enabled"
    clone_state.save()
    group = await discussion.adopt(
        tg,
        lambda marker, shape_ok: marker_candidates(tg, marker, shape_ok),
        f"{clone_state.creation_marker}-discussion",
        clone_state.discussion_destination_peer_id,
        lambda: clone_state.event("clone-init-discussion-create", {"clone_id": clone_id}),
    )
    if not discussion.is_discussion_destination(group):
        raise PolicyError("clone discussion group is not a private owned megagroup")
    clone_state.discussion_destination_peer_id = group.id
    clone_state.save()
    title = attribution.destination_title(attribution.display_name(source_group))
    if getattr(group, "title", None) != title:
        await tg(functions.channels.EditTitleRequest(channel=group, title=title))
        group.title = title
    await copy_profile(tg, source_group, group, clone_state)
    clone_state.event("clone-init-discussion-link", {"clone_id": clone_id})
    await discussion.ensure_linked(tg, destination, group)
    clone_state.discussion_linked = True
    clone_state.save()
