"""Durable send intentions and receipts shared by messages and forum topics."""

import hashlib

from telethon import errors, types

from .support import PolicyError, encode


def signature(data):
    return hashlib.sha256(encode(data).encode()).hexdigest()


def confirmed_ids(response, random_ids):
    if isinstance(response, types.UpdateShortSentMessage):
        destinations = [response.id] if len(random_ids) == 1 else []
    else:
        pairs = [
            (item.random_id, item.id)
            for item in getattr(response, "updates", ())
            if isinstance(item, types.UpdateMessageID)
        ]
        matches = dict(pairs)
        if len(pairs) != len(random_ids) or set(matches) != set(random_ids):
            raise PolicyError("Telegram did not confirm the complete cloned batch")
        destinations = [matches[key] for key in random_ids]
    if (
        len(destinations) != len(random_ids)
        or len(set(destinations)) != len(destinations)
        or any(type(item) is not int or item <= 0 for item in destinations)
    ):
        raise PolicyError("Telegram did not confirm the complete cloned batch")
    return destinations


async def submit(tg, clone, leg, source_ids, request, identity, mode, issues=None):
    random_ids = clone.prepare(leg, source_ids, signature(identity), mode, issues or {})
    if hasattr(request, "multi_media"):
        for media, random_id in zip(request.multi_media, random_ids, strict=True):
            media.random_id = random_id
    else:
        request.random_id = random_ids if isinstance(request.random_id, list) else random_ids[0]
    try:
        response = await tg(request)
    except errors.RandomIdDuplicateError:
        # Telegram remembers the request but supplied no receipt. Never allocate new IDs.
        raise PolicyError("Telegram already saw this send; inspect pending clone status") from None
    except (errors.BadRequestError, errors.ForbiddenError) as error:
        clone.store.rejected(clone.clone_id, error)
        raise
    destinations = confirmed_ids(response, random_ids)
    clone.confirm(destinations)
    clone.finish_pending()
    return destinations
