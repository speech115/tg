"""Send batches using forwards, media references, uploads or text snapshots."""

import shutil
from copy import copy

from telethon import errors, utils
from telethon.tl import functions, types

from . import attribution, fidelity, publish, quote_fallback, reforward, reupload, snapshot, topics
from .support import PolicyError
from .transfer import media_identity


def _body(message, author, plan):
    return quote_fallback.apply_body(message, author, plan)


def _reference(media):
    result = utils.get_input_media(media)
    if hasattr(result, "spoiler"):
        result.spoiler = getattr(media, "spoiler", None)
    return result


def _can_reuse(source, messages):
    return not (
        getattr(source, "noforwards", False)
        or any(getattr(message, "noforwards", False) for message in messages)
    )


def _identity(source, destination, messages, plan, author, reply_to, mode, proven):
    return {
        "source": utils.get_peer_id(source),
        "destination": destination.id,
        "mode": mode,
        "reply": reply_to,
        "proven": None if proven is None else [utils.get_peer_id(proven[0]), proven[1]],
        "messages": [
            {
                "id": message.id,
                "body": _body(message, author if i == 0 else None, plan),
                "media": media_identity(message.media),
                "kind": type(message.media).__name__,
                "spoiler": getattr(message.media, "spoiler", None),
                "forward": message.fwd_from,
                "buttons": message.reply_markup,
            }
            for i, message in enumerate(messages)
        ],
    }


def _issues(messages, plan, mode):
    result = {}
    for message in messages:
        items = []
        if plan.reply_flattened:
            items.append({"kind": "reply-flattened"})
        if plan.quote_flattened:
            items.append({"kind": "quote-fallback", **plan.quote_flattened})
        buttons = fidelity.dropped_buttons(message) if mode != "forwarded" else None
        if buttons:
            items.append({"kind": "buttons-dropped", "buttons": buttons})
        result[str(message.id)] = items
    return result


async def _media_request(
    tg, destination, clone, messages, reply_to, author, plan, progress, *, reuse
):
    cache = reupload.cache_dir(clone)

    async def input_media(message):
        if reuse:
            return _reference(message.media)
        cache.mkdir(parents=True, exist_ok=True, mode=448)
        path = await reupload.download_for_reupload(tg, message, cache, progress)
        return await reupload.uploaded_media(tg, message, path, progress)

    if len(messages) == 1:
        message = messages[0]
        text, entities = _body(message, author, plan)
        common = dict(
            peer=destination, message=text, entities=entities, random_id=0, reply_to=reply_to
        )
        if message.media is None or isinstance(message.media, types.MessageMediaWebPage):
            return functions.messages.SendMessageRequest(**common, no_webpage=message.media is None)
        return functions.messages.SendMediaRequest(**common, media=await input_media(message))
    album = []
    for index, message in enumerate(messages):
        media = await input_media(message)
        if not reuse:
            stored = await tg(functions.messages.UploadMediaRequest(peer=destination, media=media))
            media = _reference(stored)
            if hasattr(media, "spoiler"):
                media.spoiler = getattr(message.media, "spoiler", None)
        text, entities = _body(message, author if index == 0 else None, plan)
        album.append(
            types.InputSingleMedia(media=media, random_id=0, message=text, entities=entities)
        )
    return functions.messages.SendMultiMediaRequest(
        peer=destination, multi_media=album, reply_to=reply_to
    )


async def _author(tg, source, leg, message, me, author_cache, plan, proven):
    if not plan.needs_author or proven is not None:
        return None
    if leg.source_kind == "broadcast":
        if message.fwd_from is None:
            return None
        return await attribution.forwarded_author_of(tg, message, author_cache)
    return await attribution.author_of(tg, source, message, me, author_cache)


async def _snapshot_request(
    tg, source, destination, clone, message, reply_to, author, plan, capture_poll_votes, poll_votes
):
    text, entities, marker = await snapshot.render(
        tg, message, peer=source, clone_state=clone, capture_poll_votes=capture_poll_votes
    )
    if marker is not None:
        poll_votes.append(marker)
        clone.event("poll-snapshot", marker)
    text, entities = attribution.with_prefix(
        text, entities, plan.body_prefix or "", plan.body_prefix_entities
    )
    text, entities = attribution.prefixed(text, entities, author)
    return functions.messages.SendMessageRequest(
        peer=destination,
        message=text,
        entities=entities,
        random_id=0,
        reply_to=reply_to,
        no_webpage=True,
    )


async def _refresh_media(tg, source, messages):
    refreshed = await tg.get_messages(source, ids=[message.id for message in messages])
    if len(refreshed) != len(messages) or any(
        (
            fresh is None or reupload.media_key(old) != reupload.media_key(fresh)
            for old, fresh in zip(messages, refreshed, strict=True)
        )
    ):
        raise PolicyError("source media changed while copying; restart sync")
    result = [copy(message) for message in messages]
    for old, fresh in zip(result, refreshed, strict=True):
        old.media = fresh.media
    return result


async def forward_batch(
    tg,
    source,
    destination,
    clone_state,
    leg,
    messages,
    me,
    author_cache,
    plan,
    *,
    topic_dest=None,
    poll_votes=None,
    progress=None,
    reforward_cache=None,
    capture_poll_votes=False,
):
    source_ids = [message.id for message in messages]
    reply_to = copy(plan.reply_to)
    if topic_dest is not None:
        reply_to = topics.place(reply_to, topic_dest)
    proven = None
    if reforward_cache is not None and reforward.eligible(leg, messages, plan):
        proven = await reforward.locate(tg, clone_state, messages[0], reforward_cache)
    author = await _author(tg, source, leg, messages[0], me, author_cache, plan, proven)
    mode = "forwarded" if proven is not None else plan.mode
    reuse = mode == "reuploaded" and _can_reuse(source, messages)
    if reuse:
        mode = "reused"

    async def submit(request, active_mode):
        identity = _identity(
            source, destination, messages, plan, author, reply_to, active_mode, proven
        )
        if active_mode == "snapshots":
            identity["snapshot"] = request.message
        return await publish.submit(
            tg,
            clone_state,
            leg.map_field,
            source_ids,
            request,
            identity,
            active_mode,
            _issues(messages, plan, active_mode),
        )

    if mode == "forwarded":
        from_peer, ids = (proven[0], [proven[1]]) if proven else (source, source_ids)
        request = functions.messages.ForwardMessagesRequest(
            from_peer=from_peer,
            id=ids,
            random_id=[0] * len(ids),
            to_peer=destination,
            drop_author=proven is None
            and leg.source_kind == "broadcast"
            and (not any(message.fwd_from is not None for message in messages)),
            top_msg_id=None if topic_dest in (None, topics.GENERAL_TOPIC_ID) else topic_dest,
        )
    elif mode == "snapshots":
        request = await _snapshot_request(
            tg,
            source,
            destination,
            clone_state,
            messages[0],
            reply_to,
            author,
            plan,
            capture_poll_votes,
            poll_votes if poll_votes is not None else [],
        )
    else:
        request = await _media_request(
            tg, destination, clone_state, messages, reply_to, author, plan, progress, reuse=reuse
        )
    try:
        await submit(request, mode)
    except (errors.FileReferenceExpiredError, errors.FileReferenceInvalidError):
        if not reuse:
            raise
        messages = await _refresh_media(tg, source, messages)
        request = await _media_request(
            tg, destination, clone_state, messages, reply_to, author, plan, progress, reuse=False
        )
        mode = "reuploaded"
        await submit(request, mode)
    if mode == "reuploaded":
        shutil.rmtree(reupload.cache_dir(clone_state), ignore_errors=True)
    return (len(source_ids), mode, plan.reply_flattened, plan.quote_flattened)
