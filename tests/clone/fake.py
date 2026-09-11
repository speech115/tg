"""Strict in-memory Telegram peer/history service for clone workflow checks."""

from copy import copy
from datetime import UTC, datetime
from types import SimpleNamespace as NS

from telethon import utils
from telethon.tl import functions, types

NOW = datetime(2026, 9, 8, tzinfo=UTC)


def channel(peer_id=10, **kwargs):
    return types.Channel(peer_id, "Source", types.ChatPhotoEmpty(), NOW, access_hash=1, **kwargs)


def message(peer, message_id, text="hello", **kwargs):
    return types.Message(message_id, peer_id=utils.get_peer(peer), date=NOW, message=text, **kwargs)


def document(media_id=100, size=16, **kwargs):
    return types.MessageMediaDocument(
        document=types.Document(
            media_id,
            1,
            b"ref",
            NOW,
            "audio/ogg",
            size,
            1,
            [
                types.DocumentAttributeAudio(duration=12, voice=True),
                types.DocumentAttributeFilename("voice.ogg"),
            ],
        ),
        **kwargs,
    )


class Messages(list):
    def __init__(self, items, total=None):
        super().__init__(items)
        self.total = len(items) if total is None else total


class Telegram:
    def __init__(self, source, history=()):
        self.me = types.User(99, is_self=True, first_name="Owner", access_hash=1)
        self.entities, self.history, self.full = ({}, {}, {})
        self.calls, self.sent, self.downloads, self.participants = ([], [], [], [])
        self.receipts, self.uploads, self.filters, self.links = ({}, {}, [], {})
        self.fail_send = None
        self.flood_sleep_threshold = 60
        self.add(source, history)
        self.add(self.me)

    def add(self, entity, history=()):
        key = utils.get_peer_id(entity)
        self.entities[key] = entity
        self.history[key] = list(history)
        self.full[key] = NS(about="Source description", linked_chat_id=None, pinned_msg_id=None)
        return entity

    async def get_me(self):
        return self.me

    async def get_entity(self, peer):
        if isinstance(peer, str):
            found = [
                item
                for item in self.entities.values()
                if peer.lstrip("@") == getattr(item, "username", None)
            ]
            if len(found) != 1:
                raise ValueError(peer)
            return found[0]
        try:
            return self.entities[utils.get_peer_id(peer)]
        except KeyError as error:
            raise ValueError(peer) from error

    async def get_input_entity(self, peer):
        return utils.get_input_peer(await self.get_entity(peer))

    async def iter_dialogs(self):
        for entity in list(self.entities.values()):
            yield NS(entity=entity)

    async def get_messages(self, peer, *, ids=None, limit=None, **kwargs):
        values = self.history[utils.get_peer_id(peer)]
        if ids is not None:
            indexed = {item.id: item for item in values}
            return [indexed.get(i) for i in ids] if isinstance(ids, list) else indexed.get(ids)
        return Messages(sorted(values, key=lambda item: item.id, reverse=True)[:limit], len(values))

    async def iter_messages(self, peer, *, min_id=0, reverse=False, **kwargs):
        for item in sorted(
            list(self.history[utils.get_peer_id(peer)]), key=lambda row: row.id, reverse=not reverse
        ):
            if item.id > min_id:
                yield item

    async def iter_participants(self, peer):
        self.participants.append(utils.get_peer_id(peer))
        yield self.me

    async def iter_download(self, media, *, offset, request_size):
        self.downloads.append((media.document.id, offset))
        data = bytes([media.document.id % 255]) * media.document.size
        for start in range(offset, len(data), request_size):
            yield data[start : start + request_size]

    async def __call__(self, request):
        self.calls.append(request)
        handlers = {
            functions.channels.CreateChannelRequest: self.create,
            functions.channels.GetFullChannelRequest: lambda req: NS(
                full_chat=self.full[utils.get_peer_id(req.channel)]
            ),
            functions.messages.GetFullChatRequest: lambda req: NS(
                full_chat=self.full[-req.chat_id]
            ),
            functions.users.GetFullUserRequest: lambda req: NS(
                full_user=self.full[utils.get_peer_id(req.id)]
            ),
            functions.channels.EditTitleRequest: self.title,
            functions.channels.ToggleForumRequest: self.forum,
            functions.messages.EditChatAboutRequest: lambda req: True,
            functions.account.GetNotifySettingsRequest: lambda req: NS(mute_until=0),
            functions.account.UpdateNotifySettingsRequest: lambda req: True,
            functions.messages.GetDialogFiltersRequest: lambda req: self.filters,
            functions.messages.UpdateDialogFilterRequest: self.folder,
            functions.channels.SetDiscussionGroupRequest: self.link,
            functions.channels.TogglePreHistoryHiddenRequest: lambda req: True,
            functions.messages.UpdatePinnedMessageRequest: self.pin,
            functions.messages.GetDiscussionMessageRequest: self.anchor,
            functions.upload.SaveFilePartRequest: self.upload,
            functions.upload.SaveBigFilePartRequest: self.upload,
            functions.messages.UploadMediaRequest: lambda req: document(req.media.file.id),
        }
        if isinstance(
            request,
            (
                functions.messages.SendMessageRequest,
                functions.messages.SendMediaRequest,
                functions.messages.SendMultiMediaRequest,
                functions.messages.ForwardMessagesRequest,
                functions.messages.CreateForumTopicRequest,
            ),
        ):
            return self.publish(request)
        if type(request) not in handlers:
            raise AssertionError(f"unhandled fake request: {type(request).__name__}")
        return handlers[type(request)](request)

    def create(self, request):
        peer_id = 1000 + len(self.entities)
        created = channel(
            peer_id, creator=True, broadcast=request.broadcast, megagroup=request.megagroup
        )
        created.title = request.title
        self.add(
            created, [message(created, 1, action=types.MessageActionChannelCreate(request.title))]
        )
        return NS(chats=[created])

    def title(self, request):
        self.entities[utils.get_peer_id(request.channel)].title = request.title
        return True

    def forum(self, request):
        self.entities[utils.get_peer_id(request.channel)].forum = request.enabled
        return True

    def folder(self, request):
        self.filters = [request.filter]
        return True

    def link(self, request):
        self.links[utils.get_peer_id(request.broadcast)] = utils.get_peer_id(request.group)
        return True

    def pin(self, request):
        self.full[utils.get_peer_id(request.peer)].pinned_msg_id = request.id
        return True

    def anchor(self, request):
        group_key = self.links[utils.get_peer_id(request.peer)]
        match = [
            item
            for item in self.history[group_key]
            if item.fwd_from and item.fwd_from.saved_from_msg_id == request.msg_id
        ]
        return NS(messages=match)

    def upload(self, request):
        self.uploads[request.file_id, request.file_part] = request.bytes
        return True

    def publish(self, request):
        if self.fail_send == "before":
            self.fail_send = None
            raise OSError("connection lost before delivery")
        destination = getattr(request, "to_peer", None) or request.peer
        key = utils.get_peer_id(destination)
        if isinstance(request, functions.messages.SendMultiMediaRequest):
            random_ids = [item.random_id for item in request.multi_media]
            bodies = [
                message(
                    destination,
                    0,
                    item.message,
                    media=item.media,
                    entities=item.entities,
                    grouped_id=123,
                )
                for item in request.multi_media
            ]
        elif isinstance(request, functions.messages.ForwardMessagesRequest):
            random_ids = request.random_id
            indexed = {item.id: item for item in self.history[utils.get_peer_id(request.from_peer)]}
            bodies = [copy(indexed[i]) for i in request.id]
        else:
            random_ids = [request.random_id]
            bodies = [
                message(
                    destination,
                    0,
                    getattr(request, "message", ""),
                    media=getattr(request, "media", None),
                    entities=getattr(request, "entities", None),
                )
            ]
        updates = []
        for random_id, body in zip(random_ids, bodies, strict=True):
            if random_id not in self.receipts:
                body.id = max((item.id for item in self.history[key]), default=0) + 1
                body.peer_id = utils.get_peer(destination)
                body.reply_to = getattr(request, "reply_to", None)
                if isinstance(request, functions.messages.CreateForumTopicRequest):
                    body.action = types.MessageActionTopicCreate(
                        request.title, request.icon_color or 0, icon_emoji_id=request.icon_emoji_id
                    )
                self.history[key].append(body)
                self.receipts[random_id] = body.id
                self.sent.append(request)
                if key in self.links:
                    group = self.entities[self.links[key]]
                    anchor_id = len(self.history[self.links[key]]) + 1
                    self.history[self.links[key]].append(
                        message(
                            group,
                            anchor_id,
                            body.message,
                            fwd_from=types.MessageFwdHeader(
                                date=NOW,
                                saved_from_peer=utils.get_peer(destination),
                                saved_from_msg_id=body.id,
                            ),
                        )
                    )
            updates.append(types.UpdateMessageID(id=self.receipts[random_id], random_id=random_id))
        if self.fail_send == "after":
            self.fail_send = None
            raise OSError("response lost after delivery")
        return NS(updates=updates)
