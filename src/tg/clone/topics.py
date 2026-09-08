"""Create and map destination forum topics with durable send intentions."""

from telethon.tl import functions, types

from . import publish
from .support import PolicyError

GENERAL_TOPIC_ID = 1


def is_forum_destination(entity, *, title: str | None = None) -> bool:
    active = any(
        getattr(item, "active", False) for item in getattr(entity, "usernames", None) or ()
    )
    return bool(
        (title is None or getattr(entity, "title", None) == title)
        and getattr(entity, "creator", False)
        and getattr(entity, "megagroup", False)
        and (not getattr(entity, "broadcast", False))
        and (getattr(entity, "username", None) is None)
        and (not active)
    )


def create_request(marker: str):
    return functions.channels.CreateChannelRequest(
        title=marker, about="", broadcast=False, megagroup=True
    )


async def ensure_forum(tg, destination) -> None:
    if not getattr(destination, "forum", False):
        await tg(
            functions.channels.ToggleForumRequest(channel=destination, enabled=True, tabs=False)
        )
        destination.forum = True


async def create_topic(
    tg,
    destination,
    clone_state,
    source_topic_id,
    *,
    title: str,
    icon_color=None,
    icon_emoji_id=None,
) -> int:
    request = functions.messages.CreateForumTopicRequest(
        peer=destination,
        title=title,
        random_id=0,
        icon_color=icon_color,
        icon_emoji_id=icon_emoji_id,
    )
    identity = {
        "destination": destination.id,
        "title": title,
        "icon_color": icon_color,
        "icon_emoji_id": icon_emoji_id,
    }
    [destination_topic_id] = await publish.submit(
        tg, clone_state, "topic_map", [source_topic_id], request, identity, "topic"
    )
    return destination_topic_id


def topic_id_of(message) -> int:
    header = getattr(message, "reply_to", None)
    if header is None or not getattr(header, "forum_topic", False):
        return GENERAL_TOPIC_ID
    topic_id = header.reply_to_top_id
    topic_id = header.reply_to_msg_id if topic_id is None else topic_id
    if type(topic_id) is not int or not 0 < topic_id <= 2147483647:
        raise PolicyError("clone topic id is invalid")
    return topic_id


def placement_only(header) -> bool:
    return bool(
        header is not None
        and getattr(header, "forum_topic", False)
        and (header.reply_to_top_id is None)
    )


async def ensure_topic(
    tg, source, destination, clone_state, source_topic_id: int, counters: dict
) -> int:
    if source_topic_id == GENERAL_TOPIC_ID:
        return GENERAL_TOPIC_ID
    known = clone_state.topic_dest_for(source_topic_id)
    if known is not None:
        return known
    response = await tg(
        functions.messages.GetForumTopicsByIDRequest(peer=source, topics=[source_topic_id])
    )
    found = [
        item
        for item in getattr(response, "topics", ())
        if getattr(item, "id", None) == source_topic_id
        and isinstance(getattr(item, "title", None), str)
        and item.title
    ]
    if len(found) != 1:
        raise PolicyError("Telegram did not return exactly one valid topic")
    counters["topics_created"] += 1
    return await create_topic(
        tg,
        destination,
        clone_state,
        source_topic_id,
        title=found[0].title,
        icon_color=found[0].icon_color,
        icon_emoji_id=found[0].icon_emoji_id,
    )


def place(reply_to, destination_topic_id: int):
    if destination_topic_id == GENERAL_TOPIC_ID:
        return reply_to
    if reply_to is None:
        return types.InputReplyToMessage(reply_to_msg_id=destination_topic_id)
    reply_to.top_msg_id = destination_topic_id
    return reply_to
