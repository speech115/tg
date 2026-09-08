"""Full chat cloning using an existing Telethon client and a scoped Store."""

import secrets
import time
from datetime import UTC, datetime

from telethon import errors as telethon_errors
from telethon.errors import MessageNotModifiedError
from telethon.tl import functions, types

from . import (
    attribution,
    batching,
    discussion,
    ergonomics,
    init_peers,
    pin,
    quotes,
    replies,
    roster,
    state,
    topics,
)
from . import progress as clone_progress
from . import refresh as clone_refresh
from . import send as clone_send
from .support import PolicyError, note

WINDOW = 50


async def _resolve_destination(tg, destination_peer_id: int):
    try:
        return await tg.get_entity(types.PeerChannel(destination_peer_id))
    except discussion.PEER_UNAVAILABLE:
        raise PolicyError("clone destination is unavailable") from None


def _record_destination_name(clone_state, destination) -> None:
    """Remember what the destination is called, for the offline status listing."""
    clone_state.destination_title = getattr(destination, "title", None)
    clone_state.destination_username = getattr(destination, "username", None)


async def _resolve_source(tg, store, source: str, *, account_user_id: int | None = None):
    """Resolve SOURCE to an entity. Pass ``account_user_id`` where a clone must already
    exist, so a title can be answered from state instead of Telegram."""
    kind, separator, number = source.partition(":")
    peer_types = {"user": types.PeerUser, "chat": types.PeerChat, "channel": types.PeerChannel}
    if separator and kind in peer_types and number.isdecimal():
        ref = peer_types[kind](state.valid_id(int(number), 2**63 - 1))
    else:
        ref = recorded_source_ref(store, account_user_id, source) if account_user_id else None
        if ref is None:
            ref = int(source) if source.lstrip("-").isdigit() else source
    try:
        entity = await tg.get_entity(ref)
    except discussion.PEER_UNAVAILABLE:
        raise PolicyError(f"clone source not found: {source!r}") from None
    kind = attribution.source_kind(entity)
    return (entity, kind, attribution.display_name(entity))


def _supersede_status(store, clone_id: str, replace: bool) -> dict:
    """Read saved clone availability for the initialization preview."""
    try:
        existing = store.load(clone_id) is not None
        readable = True if existing else None
    except PolicyError:
        existing, readable = (True, False)
    return {"existing": existing, "readable": readable, "replace": replace}


async def preview_init(
    tg, store, me, source: str, *, replace: bool = False, no_comments: bool = False
) -> dict:
    entity, source_kind, source_title = await _resolve_source(tg, store, source)
    total = (await tg.get_messages(entity, limit=0)).total
    clone_id = state.clone_id(me.id, entity.id, source_kind)
    peers_to_create = await _peers_to_create(
        tg, store, entity, source_kind, clone_id, no_comments=no_comments, replace=replace
    )
    preview = store.preview(
        {
            "kind": "clone-init",
            "source": source,
            "account_user_id": me.id,
            "source_peer_id": entity.id,
            "source_title": source_title,
            "source_kind": source_kind,
            "replace": replace,
            "no_comments": no_comments,
            "protected": bool(getattr(entity, "noforwards", False)),
            "approximate_message_count": total,
        }
    )
    return {
        "preview_id": preview["preview_id"],
        "expires_at": preview["expires_at"],
        "clone": {
            "id": clone_id,
            "source": {"id": entity.id, "title": source_title, "kind": source_kind},
            "destination": None,
            "status": "planned",
            "commit_required": True,
        },
        "approximate_message_count": total,
        "protected": bool(getattr(entity, "noforwards", False)),
        "supersede": _supersede_status(store, clone_id, replace),
        "peers_to_create": peers_to_create,
    }


async def _peers_to_create(
    tg, store, entity, source_kind, clone_id, *, no_comments: bool, replace: bool = False
) -> int:
    try:
        existing = store.load(clone_id)
    except PolicyError:
        existing = None
    active = None if replace else existing
    count = int(active is None or active.destination_peer_id is None)
    if (
        no_comments
        or source_kind != "broadcast"
        or active is not None
        and (active.comments == "disabled" or active.discussion_destination_peer_id is not None)
    ):
        return count
    full = await tg(functions.channels.GetFullChannelRequest(entity))
    return count + int(discussion.linked_chat_id(full.full_chat) is not None)


async def _init_destination(tg, clone_state, shape_ok, kind_name):
    marker = clone_state.creation_marker
    clone_id = clone_state.clone_id
    forum = clone_state.destination_kind == "forum"
    if clone_state.destination_peer_id is not None:
        destination = await _resolve_destination(tg, clone_state.destination_peer_id)
        if not shape_ok(destination):
            raise PolicyError(f"clone destination is not a private owned {kind_name}")
    else:
        valid, wrong_shape = await init_peers.marker_candidates(tg, marker, shape_ok)
        if len(valid) + len(wrong_shape) > 1:
            raise PolicyError("clone destination marker matched multiple channels")
        if wrong_shape:
            raise PolicyError("clone destination marker matched a channel with wrong shape")
        if valid:
            destination = valid[0]
        else:
            clone_state.event("clone-init-create", {"clone_id": clone_id})
            update = await tg(
                topics.create_request(marker)
                if forum
                else functions.channels.CreateChannelRequest(
                    title=marker, about="", broadcast=True, megagroup=False
                )
            )
            candidates = [
                item for item in getattr(update, "chats", ()) if shape_ok(item, title=marker)
            ]
            if len(candidates) != 1:
                raise PolicyError("Telegram did not return the created private channel")
            destination = candidates[0]
        clone_state.destination_peer_id = destination.id
        clone_state.save()
    return destination


async def _apply_ergonomics(tg, clone_state, destination):
    peers = [destination]
    discussion_unresolved = False
    if clone_state.discussion_destination_peer_id is not None:
        try:
            peers.append(
                await tg.get_entity(types.PeerChannel(clone_state.discussion_destination_peer_id))
            )
        except telethon_errors.FloodWaitError:
            raise
        except (ValueError, telethon_errors.RPCError):
            discussion_unresolved = True
            note(
                f"warning: unresolved discussion peer {clone_state.discussion_destination_peer_id}"
            )
    applied = await ergonomics.apply(tg, peers)
    if discussion_unresolved:
        applied["muted"] = False
    return applied


async def commit_init(tg, store, me, source: str, payload: dict) -> dict:
    replace = bool(payload.get("replace"))
    entity, source_kind, _ = await _resolve_source(tg, store, source)
    if (
        me.id != payload["account_user_id"]
        or entity.id != payload["source_peer_id"]
        or payload.get("source_kind", source_kind) != source_kind
    ):
        raise PolicyError("clone init preview no longer matches the source or account")
    clone_id = state.clone_id(me.id, entity.id, source_kind)
    existing = store.load(clone_id)
    if replace and existing is not None:
        archived = store.archive(existing)
        store.event("clone-replaced", {"archive": archived}, clone_id)
        existing = None
    clone_state = existing or store.create(me.id, entity.id, payload["source_title"], source_kind)
    if clone_state.source_kind != source_kind:
        raise PolicyError("clone source kind no longer matches initialized state")
    no_comments = bool(payload.get("no_comments")) or clone_state.comments == "disabled"
    if no_comments and clone_state.comments == "enabled":
        raise PolicyError(
            "no-comments cannot disable an existing linked discussion; "
            "use init --replace for a fresh clone"
        )
    if clone_state.creation_marker is None:
        nonce = f"-{secrets.token_hex(3)}" if replace else ""
        clone_state.creation_marker = f"tg-clone-{clone_id[:12]}{nonce}"
    clone_state.save()
    forum = clone_state.destination_kind == "forum"
    shape_ok = topics.is_forum_destination if forum else init_peers.is_private_owned_broadcast
    kind_name = "forum megagroup" if forum else "broadcast channel"
    destination = await _init_destination(tg, clone_state, shape_ok, kind_name)
    if forum and (not getattr(destination, "forum", False)):
        clone_state.event("clone-init-forum", {"clone_id": clone_id})
    if forum:
        await topics.ensure_forum(tg, destination)
    titled = attribution.destination_title(clone_state.source_title)
    if getattr(destination, "title", None) != titled:
        clone_state.event("clone-init-title", {"clone_id": clone_id})
        await tg(functions.channels.EditTitleRequest(channel=destination, title=titled))
        destination.title = titled
    _record_destination_name(clone_state, destination)
    clone_state.save()
    full_chat = await init_peers.copy_profile(tg, entity, destination, clone_state)
    if no_comments:
        clone_state.comments = "disabled"
        clone_state.save()
    else:
        await init_peers.init_discussion(tg, destination, clone_state, full_chat, clone_id)
    applied = await _apply_ergonomics(tg, clone_state, destination)
    clone_state.initialized = True
    clone_state.save()
    return {
        "clone": {
            "id": clone_state.clone_id,
            "source": {
                "id": clone_state.source_peer_id,
                "title": clone_state.source_title,
                "kind": clone_state.source_kind,
            },
            "destination": {
                "id": clone_state.destination_peer_id,
                "title": getattr(destination, "title", titled),
            },
            "comments": clone_state.comments,
            "status": "ready",
            "commit_required": False,
        },
        "ergonomics": applied,
    }


def _description(clone, destination=None):
    result = {
        "id": clone.clone_id,
        "source": {
            "id": clone.source_peer_id,
            "title": clone.source_title,
            "kind": clone.source_kind,
        },
    }
    if destination is not None:
        result["destination"] = {"id": destination.id, "title": destination.title}
    return result


def _check_destination(destination, clone_state):
    forum = clone_state.destination_kind == "forum"
    valid_destination = (
        topics.is_forum_destination(destination) and getattr(destination, "forum", False)
        if forum
        else init_peers.is_private_owned_broadcast(destination)
    )
    if not valid_destination:
        kind_name = "forum megagroup" if forum else "broadcast channel"
        raise PolicyError(f"clone destination is not a private owned {kind_name}")


async def sync_text(
    tg,
    store,
    me,
    source: str,
    *,
    limit: int | None = None,
    max_runtime: float | None = None,
    capture_poll_votes: bool = False,
) -> dict:
    source_entity, clone_state = await _load_clone(tg, store, me, source)
    if clone_state.comments == "enabled" and (not clone_state.discussion_linked):
        raise PolicyError("discussion is not linked yet; repeat init and commit its preview")
    clone_state.finish_pending()
    destination = await _resolve_destination(tg, clone_state.destination_peer_id)
    _record_destination_name(clone_state, destination)
    clone_state.save()
    _check_destination(destination, clone_state)
    await discussion.verify_tail(
        tg,
        destination,
        clone_state.max_destination_id(),
        "destination",
        lambda item: (
            getattr(item, "action", None) is not None
            and (
                not (
                    isinstance(item.action, types.MessageActionTopicCreate)
                    and item.id not in clone_state.topic_map.values()
                )
            )
        ),
    )
    return await Sync(
        tg, clone_state, me, source_entity, destination, limit, max_runtime, capture_poll_votes
    ).run()


class Sync:
    def __init__(self, tg, clone, me, source, destination, limit, runtime, capture_votes):
        self.tg, self.clone, self.me = (tg, clone, me)
        self.source, self.destination = (source, destination)
        self.limit = limit
        self.deadline = None if runtime is None else time.monotonic() + runtime
        self.capture_votes = capture_votes
        self.forum = clone.destination_kind == "forum"
        self.posts = clone.leg()
        self.resolve = quotes.ResolveContext(tg=tg, destination=destination)
        self.progress = clone_progress.SyncProgress(source.id, clone=clone)
        self.copied = self.batches = self.reply_flattened = 0
        self.unsupported, self.quote_flattened, self.markup_dropped, self.poll_votes = (
            [],
            [],
            [],
            [],
        )
        self.transports = dict.fromkeys(("forwarded", "reused", "reuploaded", "snapshots"), 0)
        self.counters = dict.fromkeys(
            ("topics_created", "skipped_service", "skipped_autoforward"), 0
        )
        self.author_cache, self.reforward_cache = ({}, {})
        self.posts_exhausted = self.more = False

    def timed_out(self):
        return self.deadline is not None and time.monotonic() >= self.deadline

    def limited(self):
        return self.timed_out() or (self.limit is not None and self.batches >= self.limit)

    def skip_unsupported(self, messages, leg):
        unsupported = [
            {"id": message.id, "kind": kind}
            for message in messages
            if (kind := batching.unsupported_kind(message)) is not None
        ]
        if not unsupported:
            return False
        self.unsupported.extend(unsupported)
        for message in messages:
            self.clone.outcome(
                leg.map_field,
                message.id,
                status="skipped",
                reason=batching.unsupported_kind(message) or "unsupported-album",
            )
        leg.cursor = messages[-1].id
        self.clone.save()
        return True

    def record_result(self, messages, result):
        count, mode, flattened, quote = result
        self.copied += count
        self.batches += 1
        self.transports[mode] += count
        self.reply_flattened += int(flattened)
        if quote:
            self.quote_flattened.append(quote)
        if mode != "forwarded":
            self.markup_dropped.extend(
                {"id": message.id, "buttons": buttons}
                for message in messages
                if (buttons := batching.dropped_buttons(message))
            )
        self.progress.batch(count, mode)

    async def copy_batch(self, messages, leg, source, destination, plan=None):
        if self.skip_unsupported(messages, leg):
            return
        await self.progress.resolve_total(self.tg, source)
        plan = plan or replies.decide(
            messages,
            leg,
            source,
            posts_cursor=self.clone.cursor,
            posts_exhausted=self.posts_exhausted,
        )
        plan = await quotes.resolve(messages, plan, leg, self.resolve)
        if plan.mode == "deferred":
            return
        topic = None
        if self.forum:
            topic = await topics.ensure_topic(
                self.tg,
                source,
                destination,
                self.clone,
                topics.topic_id_of(messages[0]),
                self.counters,
            )
        result = await quotes.send_with_degrade(
            lambda active: clone_send.forward_batch(
                self.tg,
                source,
                destination,
                self.clone,
                leg,
                list(messages),
                self.me,
                self.author_cache,
                active,
                topic_dest=topic,
                poll_votes=self.poll_votes,
                progress=self.progress,
                reforward_cache=self.reforward_cache,
                capture_poll_votes=self.capture_votes,
            ),
            list(messages),
            plan,
            leg,
            self.resolve,
        )
        self.record_result(messages, result)

    async def service(self, event):
        message = event.message
        if self.forum and isinstance(message.action, types.MessageActionTopicCreate):
            if self.clone.topic_dest_for(message.id) is None:
                await topics.create_topic(
                    self.tg,
                    self.destination,
                    self.clone,
                    message.id,
                    title=message.action.title,
                    icon_color=message.action.icon_color,
                    icon_emoji_id=message.action.icon_emoji_id,
                )
                self.counters["topics_created"] += 1
        else:
            self.counters["skipped_service"] += 1
            self.clone.outcome("id_map", message.id, status="skipped", reason="service")
        self.posts.cursor = message.id
        self.clone.save()

    async def posts_window(self, maximum):
        self.progress.phase("posts", copied=len(self.clone.id_map))
        ran = 0
        async for event in batching.plan(
            self.tg.iter_messages(self.source, min_id=self.posts.cursor, reverse=True)
        ):
            if self.limited():
                self.more = True
                return
            if isinstance(event, batching.ServiceSkip):
                await self.service(event)
                continue
            await self.copy_batch(event.messages, self.posts, self.source, self.destination)
            ran += 1
            if maximum is not None and ran >= maximum:
                return
        self.posts_exhausted = True

    async def comments_window(self):
        self.progress.phase("comments", copied=len(self.clone.discussion_id_map))
        leg, ctx = self.clone.leg(discussion=True), self.resolve
        self.more = False
        async for event in discussion.comment_events(
            self.tg, self.clone, self.source, self.destination, ctx
        ):
            if self.limited():
                self.more = True
                return
            if isinstance(event, batching.ServiceSkip):
                self.counters["skipped_service"] += 1
                leg.cursor = event.message_id
            elif (posts := discussion.anchor_posts(event.messages, self.source.id)) is not None:
                if not self.posts_exhausted and any(p > self.clone.cursor for p in posts.values()):
                    return
                ctx.anchors.update(posts)
                self.counters["skipped_autoforward"] += len(posts)
                leg.cursor = event.messages[-1].id
            else:
                plan = replies.decide(
                    event.messages,
                    leg,
                    ctx.source_group,
                    posts_cursor=self.clone.cursor,
                    posts_exhausted=self.posts_exhausted,
                )
                if plan.mode == "deferred":
                    return
                await self.copy_batch(
                    event.messages, leg, ctx.source_group, ctx.destination_group, plan
                )
                continue
            self.clone.save()

    async def run(self):
        pending = self.clone.store.pending(self.clone.clone_id)
        if pending and pending["leg"] == "discussion_id_map":
            await self.comments_window()
        while not self.more and (not self.timed_out()) and (not self.posts_exhausted):
            linked = self.clone.comments == "enabled"
            await self.posts_window(WINDOW if linked else None)
            if linked and (not self.more) and (not self.timed_out()):
                await self.comments_window()
        pinned = await self.finish()
        self.clone.last_synced_at = datetime.now(UTC).isoformat()
        self.clone.save()
        return self.result(pinned)

    async def finish(self):
        pinned = None
        if not self.forum:
            pinned = pin.snapshot(self.clone)
            if not self.more and (not self.timed_out()):
                pinned = await pin.sync_phase(self.tg, self.clone, self.source, self.destination)
        if not self.more and (not self.timed_out()) and (self.clone.participants is None):
            self.progress.phase("roster")
            self.clone.participants = await roster.collect(self.tg, self.clone, self.source)
        return pinned

    def result(self, pinned):
        data = {
            "clone": {
                **_description(self.clone, self.destination),
                "comments": self.clone.comments,
            },
            "sync": {
                "copied": self.copied,
                "skipped_unsupported": self.unsupported,
                **self.transports,
                **self.counters,
                "reply_flattened": self.reply_flattened,
                "quote_flattened": self.quote_flattened,
                "markup_dropped": self.markup_dropped,
                "poll_votes": self.poll_votes,
                "cursor": self.clone.cursor,
                "discussion_cursor": self.clone.discussion_cursor,
                "more": self.more,
                "participants": self.clone.participants,
            },
            "remaining": self.more or self.timed_out(),
            "degraded": bool(
                self.unsupported
                or self.quote_flattened
                or self.markup_dropped
                or self.reply_flattened
                or self.clone.comments == "unavailable"
            ),
        }
        if pinned is not None:
            data["sync"]["pinned"] = pinned
        if self.timed_out():
            data["stop_reason"] = "wall_clock_cap"
        return data


async def _load_clone(tg, store, me, source):
    source_entity, source_kind, _ = await _resolve_source(tg, store, source, account_user_id=me.id)
    clone_state = store.load(state.clone_id(me.id, source_entity.id, source_kind))
    if clone_state is None or clone_state.destination_peer_id is None:
        raise PolicyError("clone is not initialized; run clone init first")
    if clone_state.source_kind != source_kind:
        raise PolicyError("clone source kind no longer matches initialized state")
    return source_entity, clone_state


async def _load_refresh_context(tg, store, me, source: str):
    source_entity, clone_state = await _load_clone(tg, store, me, source)
    destination = await _resolve_destination(tg, clone_state.destination_peer_id)
    _check_destination(destination, clone_state)
    return (me, source_entity, destination, clone_state)


async def preview_refresh(tg, store, me, source: str) -> dict:
    me, source_entity, destination, clone_state = await _load_refresh_context(tg, store, me, source)
    eligible, excluded = await clone_refresh.candidates(
        tg, clone_state, source_entity, destination, me
    )
    pairs = [
        {"source_id": item.source_id, "destination_id": item.destination_id} for item in eligible
    ]
    preview = store.preview(
        {
            "kind": "clone-refresh",
            "clone_id": clone_state.clone_id,
            "source": source,
            "account_user_id": me.id,
            "source_peer_id": source_entity.id,
            "eligible": pairs,
        }
    )
    return {
        "preview_id": preview["preview_id"],
        "expires_at": preview["expires_at"],
        "clone": _description(clone_state),
        "refresh": {
            "eligible": pairs,
            "excluded": [{"source_id": item.source_id, "reason": item.reason} for item in excluded],
        },
    }


async def commit_refresh(tg, store, me, source: str, payload: dict) -> dict:
    me, source_entity, destination, clone_state = await _load_refresh_context(tg, store, me, source)
    if (
        me.id != payload["account_user_id"]
        or source_entity.id != payload["source_peer_id"]
        or clone_state.clone_id != payload["clone_id"]
    ):
        raise PolicyError("clone refresh preview no longer matches the source or account")
    eligible = list(payload.get("eligible") or ())
    for pair in eligible:
        if clone_state.dest_for(int(pair["source_id"])) != int(pair["destination_id"]):
            raise PolicyError("clone refresh preview no longer matches the current id_map")
    input_peer = await tg.get_input_entity(destination)
    author_cache: dict = {}
    edited: list[dict] = []
    skipped: list[dict] = []
    for pair in eligible:
        source_id = pair["source_id"]
        destination_id = pair["destination_id"]
        source_msgs = await tg.get_messages(source_entity, ids=[source_id])
        dest_msgs = await tg.get_messages(destination, ids=[destination_id])
        message = source_msgs[0] if source_msgs else None
        dest = dest_msgs[0] if dest_msgs else None
        if message is None or dest is None:
            skipped.append({"source_id": source_id, "reason": "not-eligible"})
            continue
        rendered_text, rendered_entities = await clone_refresh.render_with_current_rules(
            tg, source_entity, message, me, clone_state.source_kind, author_cache
        )
        dest_text = getattr(dest, "message", None) or ""
        dest_entities = getattr(dest, "entities", None)
        if not clone_refresh.eligible_for_backfill(
            message, dest_text, dest_entities, rendered_text, rendered_entities
        ):
            skipped.append({"source_id": source_id, "reason": "not-eligible"})
            continue
        clone_state.event(
            "clone-refresh-prefix",
            {
                "clone_id": clone_state.clone_id,
                "source_message_id": source_id,
                "destination_message_id": destination_id,
            },
        )
        try:
            await tg(
                functions.messages.EditMessageRequest(
                    peer=input_peer,
                    id=destination_id,
                    message=rendered_text,
                    entities=rendered_entities,
                )
            )
        except MessageNotModifiedError:
            pass
        edited.append({"source_id": source_id, "destination_id": destination_id})
    return {
        "clone": _description(clone_state, destination),
        "refresh": {"edited": edited, "skipped": skipped, "count": len(edited)},
    }


def recorded_source_ref(store, account_id, source):
    matches = [
        clone
        for clone in store.all()
        if clone.account_user_id == account_id and source_matches(clone, source)
    ]
    if len(matches) > 1:
        raise PolicyError("source matches multiple clones; use a typed peer ID")
    if not matches:
        return None
    clone = matches[0]
    cls = {"user": types.PeerUser, "chat": types.PeerChat, "channel": types.PeerChannel}
    return cls[state.PEER_CLASS[clone.source_kind]](clone.source_peer_id)


def source_matches(clone, source):
    if source is None:
        return True
    if source == clone.clone_id:
        return True
    kind, separator, identifier = source.partition(":")
    if separator and kind in {"user", "chat", "channel"} and identifier.isdecimal():
        return state.PEER_CLASS[clone.source_kind] == kind and clone.source_peer_id == int(
            identifier
        )
    if source.lstrip("-").isdecimal():
        from telethon.utils import resolve_id

        peer_id, peer_class = resolve_id(int(source))
        if peer_id != clone.source_peer_id:
            return False
        return (
            int(source) >= 0
            or peer_class.__name__.removeprefix("Peer").lower()
            == state.PEER_CLASS[clone.source_kind]
        )
    return source.casefold() in clone.source_title.casefold()
