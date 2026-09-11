import asyncio
from copy import copy
from types import SimpleNamespace as NS

import pytest
from telethon import errors, utils
from telethon.tl import functions, types

from tg.clone import Store, reforward, replies, snapshot
from tg.clone.__main__ import status
from tg.clone.support import PolicyError

from .fake import NOW, Telegram, channel, document, message
from .test_workflow import call, initialize


def test_rejected_foreign_quote_keeps_text_formatting_and_persists_losses(tmp_path):
    source = channel(broadcast=True, noforwards=True)
    foreign = channel(20, broadcast=True)
    foreign.title = "Foreign"
    original = message(
        source,
        2,
        "😀 body",
        entities=[types.MessageEntityBold(3, 4)],
        reply_markup=types.ReplyInlineMarkup(
            [types.KeyboardButtonRow([types.KeyboardButtonCallback("Button", b"payload")])]
        ),
        reply_to=types.MessageReplyHeader(
            reply_to_msg_id=10, reply_to_peer_id=types.PeerChannel(20), quote_text="😀 quote"
        ),
    )

    class Rejected(Telegram):
        def publish(self, request):
            if getattr(request.reply_to, "reply_to_peer_id", None) is not None:
                raise errors.ChannelPrivateError(request)
            return super().publish(request)

    tg = Rejected(source, [original])
    tg.add(foreign, [message(foreign, 10)])
    initialize(tg, tmp_path)
    result = call(tg, tmp_path, "sync", "channel:10")
    assert result["degraded"] and len(result["sync"]["markup_dropped"]) == 1
    sent = tg.sent[-1]
    assert "Foreign" in sent.message and "😀 quote" in sent.message
    assert "id unknown" not in sent.message
    assert original.entities[0].offset == 3
    bold = next(entity for entity in sent.entities if isinstance(entity, types.MessageEntityBold))
    assert (
        sent.message.encode("utf-16-le")[bold.offset * 2 : (bold.offset + bold.length) * 2].decode(
            "utf-16-le"
        )
        == "body"
    )
    with Store(tmp_path, readonly=True) as store:
        [row] = status(store)
        assert row["outcomes"]["degraded"] == 1
        assert len(row["recent_losses"][0]["issues"]) == 2
        assert row["pending"] is None


def test_typed_peer_collision_does_not_remap_foreign_user(tmp_path):
    source = channel(broadcast=True)
    with Store(tmp_path) as store:
        clone = store.create(99, 10, "Source", "broadcast")
        clone.discussion_source_peer_id = 11
        clone.record_discussion_mapping(2, 200)
        clone.save()
        item = message(
            source,
            3,
            reply_to=types.MessageReplyHeader(
                reply_to_msg_id=2, reply_to_peer_id=types.PeerUser(11)
            ),
        )
        assert replies.target([item], clone.leg(), source).kind == "foreign-peer"


def test_reforward_requires_identical_formatting_and_spoiler(tmp_path):
    source = channel(broadcast=True, noforwards=True)
    group = channel(11, megagroup=True)
    sender = types.User(42, first_name="Sender", access_hash=1)
    original = message(
        group,
        7,
        "same",
        from_id=types.PeerUser(42),
        media=document(spoiler=True),
        entities=[types.MessageEntityBold(0, 4)],
    )
    repost = message(
        source,
        2,
        "same",
        media=document(spoiler=True),
        entities=[types.MessageEntityBold(0, 4)],
        fwd_from=types.MessageFwdHeader(date=NOW, from_id=types.PeerUser(42)),
    )
    tg = Telegram(source, [repost])
    tg.add(group, [original])
    tg.add(sender)
    with Store(tmp_path) as store:
        clone = store.create(99, 10, "Source", "broadcast")
        clone.discussion_source_peer_id = 11
        clone.save()
        plan = replies.decide([repost], clone.leg(), source)
        assert reforward.eligible(clone.leg(), [repost], plan)
        found = asyncio.run(reforward.locate(tg, clone, repost, {}))
        assert found == (group, 7)
        original.entities = [types.MessageEntityItalic(0, 4)]
        assert asyncio.run(reforward.locate(tg, clone, repost, {})) is None
        original.entities = repost.entities
        original.media.spoiler = False
        assert asyncio.run(reforward.locate(tg, clone, repost, {})) is None


def test_expired_media_reference_refreshes_before_upload(tmp_path):
    source = channel(broadcast=True)

    class Expired(Telegram):
        def publish(self, request):
            if isinstance(getattr(request, "media", None), types.InputMediaDocument):
                raise errors.FileReferenceExpiredError(request)
            return super().publish(request)

    tg = Expired(
        source,
        [
            message(source, 2),
            message(
                source, 3, media=document(), reply_to=types.MessageReplyHeader(reply_to_msg_id=2)
            ),
        ],
    )
    initialize(tg, tmp_path)
    result = call(tg, tmp_path, "sync", "channel:10")
    assert result["sync"]["forwarded"] == 1 and result["sync"]["reuploaded"] == 1
    assert tg.sent[-1].reply_to.reply_to_msg_id == 2
    assert len(tg.downloads) == 1


def test_refresh_checks_destination_and_current_text_before_editing(tmp_path):
    source = channel(broadcast=True)
    repost = message(
        source, 2, "body", fwd_from=types.MessageFwdHeader(date=NOW, from_name="Alice")
    )

    class Editable(Telegram):
        async def __call__(self, request):
            if isinstance(request, functions.messages.EditMessageRequest):
                self.calls.append(request)
                item = await self.get_messages(request.peer, ids=request.id)
                item.message, item.entities = (request.message, request.entities)
                return True
            return await super().__call__(request)

    tg = Editable(source, [repost])
    created = initialize(tg, tmp_path)
    dest = tg.entities[utils.get_peer_id(types.PeerChannel(created["clone"]["destination"]["id"]))]
    tg.history[utils.get_peer_id(dest)].append(message(dest, 2, "body"))
    with Store(tmp_path) as store:
        clone = store.all()[0]
        clone.record_mapping(2, 2)
        clone.cursor = 2
        clone.save()
    preview = call(tg, tmp_path, "refresh", "channel:10")
    assert len(preview["refresh"]["eligible"]) == 1
    assert tg.history[utils.get_peer_id(dest)][-1].message == "body"
    result = call(tg, tmp_path, "refresh", "channel:10", "--commit", preview["preview_id"])
    assert result["refresh"]["count"] == 1
    assert tg.history[utils.get_peer_id(dest)][-1].message.startswith("Переслано от Alice")
    assert call(tg, tmp_path, "refresh", "channel:10")["refresh"]["eligible"] == []
    dest.username = "public_now"
    with pytest.raises(PolicyError, match="private owned"):
        call(tg, tmp_path, "refresh", "channel:10")


def test_unsupported_media_and_story_snapshot_survive_restart(tmp_path):
    source = channel(broadcast=True)
    tg = Telegram(
        source,
        [
            message(source, 2, media=types.MessageMediaDice(1, "🎲")),
            message(source, 3, media=types.MessageMediaStory(types.PeerUser(99), 10)),
        ],
    )
    initialize(tg, tmp_path)
    result = call(tg, tmp_path, "sync", "channel:10")
    assert result["sync"]["snapshots"] == 1
    assert result["sync"]["skipped_unsupported"] == [{"id": 2, "kind": "MessageMediaDice"}]
    assert "Owner" in tg.sent[-1].message
    with Store(tmp_path, readonly=True) as store:
        assert status(store)[0]["recent_losses"][0]["reason"] == "MessageMediaDice"


def test_source_discussion_change_preserves_old_map(tmp_path):
    source, group, different = (
        channel(broadcast=True),
        channel(11, megagroup=True),
        channel(12, megagroup=True),
    )
    tg = Telegram(source)
    tg.add(group)
    tg.add(different)
    tg.full[utils.get_peer_id(source)].linked_chat_id = 11
    initialize(tg, tmp_path)
    with Store(tmp_path) as store:
        clone = store.all()[0]
        clone.record_discussion_mapping(2, 20)
        clone.discussion_cursor = 2
        clone.save()
    tg.full[utils.get_peer_id(source)].linked_chat_id = 12
    with pytest.raises(PolicyError, match="discussion group changed"):
        initialize(tg, tmp_path)
    with Store(tmp_path, readonly=True) as store:
        clone = store.all()[0]
        assert clone.discussion_source_peer_id == 11 and clone.discussion_dest_for(2) == 20


def test_poll_capture_excludes_non_retractable_polls():
    base = NS(
        closed=False,
        quiz=False,
        public_voters=False,
        revoting_disabled=False,
        hide_results_until_close=False,
    )
    assert snapshot._poll_eligible_for_vote(base)
    for flag in (
        "closed",
        "quiz",
        "public_voters",
        "revoting_disabled",
        "hide_results_until_close",
    ):
        poll = copy(base)
        setattr(poll, flag, True)
        assert not snapshot._poll_eligible_for_vote(poll)


def test_avatar_thumbnail_and_media_shapes_are_preserved(tmp_path):
    from tg.clone import media
    from tg.clone.media import _photo_with_largest_size_last

    source = channel(broadcast=True)
    source.photo = NS(photo_id=777)

    class Photos(Telegram):
        avatar_downloads = 0

        async def download_profile_photo(self, entity, *, file):
            self.avatar_downloads += 1
            file.write_bytes(b"photo")
            return str(file)

        async def download_media(self, item, *, file, thumb):
            assert thumb.type == "large"
            file.write_bytes(b"thumbnail")
            return str(file)

        async def upload_file(self, path):
            return types.InputFile(500, 1, str(path), "checksum")

        async def __call__(self, request):
            if isinstance(request, functions.channels.EditPhotoRequest):
                self.calls.append(request)
                return True
            return await super().__call__(request)

    tg = Photos(source)
    initialize(tg, tmp_path)
    initialize(tg, tmp_path)
    assert tg.avatar_downloads == 1
    item = message(source, 2, media=document())
    item.media.document.thumbs = [
        types.PhotoPathSize("outline", b"path"),
        types.PhotoSize("small", 20, 20, 10),
        types.PhotoSize("large", 40, 40, 100),
    ]
    path = tmp_path / "media.bin"
    path.write_bytes(b"data")
    uploaded = asyncio.run(media.uploaded_media(tg, item, path))
    assert uploaded.thumb.id == 500 and uploaded.attributes[0].voice
    photo = types.Photo(
        9,
        1,
        b"ref",
        NOW,
        [types.PhotoSize("big", 100, 100, 1000), types.PhotoSize("small", 10, 10, 10)],
        1,
    )
    media = types.MessageMediaPhoto(photo=photo, spoiler=True)
    reordered = _photo_with_largest_size_last(media)
    assert reordered.photo.sizes[-1].type == "big" and reordered.spoiler
    assert photo.sizes[-1].type == "small"


def test_inaccessible_comments_keep_existing_cursor_and_mappings(tmp_path):
    source, group = channel(broadcast=True), channel(11, megagroup=True)

    class PrivateGroup(Telegram):
        unavailable = False

        async def get_entity(self, peer):
            if self.unavailable and isinstance(peer, types.PeerChannel) and peer.channel_id == 11:
                raise errors.ChannelPrivateError(None)
            return await super().get_entity(peer)

    tg = PrivateGroup(source)
    tg.add(group)
    tg.full[utils.get_peer_id(source)].linked_chat_id = 11
    initialize(tg, tmp_path)
    with Store(tmp_path) as store:
        clone = store.all()[0]
        clone.record_discussion_mapping(2, 20)
        clone.discussion_cursor = 2
        clone.save()
    tg.unavailable = True
    result = call(tg, tmp_path, "sync", "channel:10")
    assert result["degraded"] and result["clone"]["comments"] == "unavailable"
    with Store(tmp_path, readonly=True) as store:
        clone = store.all()[0]
        assert clone.discussion_cursor == 2 and clone.discussion_dest_for(2) == 20


def test_comment_reply_to_album_member_keeps_thread(tmp_path):
    source, group = channel(broadcast=True), channel(11, megagroup=True)

    class AlbumDiscussion(Telegram):
        def anchor(self, request):
            if request.msg_id != 2:
                raise errors.MsgIdInvalidError(request)
            items = self.history[self.links[utils.get_peer_id(request.peer)]]
            return NS(messages=list(reversed([m for m in items if m.fwd_from])))

    tg = AlbumDiscussion(
        source, [message(source, i, media=document(i), grouped_id=77) for i in (2, 3)]
    )
    anchors = [
        message(
            group,
            i,
            media=document(i),
            grouped_id=77,
            fwd_from=types.MessageFwdHeader(
                date=NOW, saved_from_peer=types.PeerChannel(10), saved_from_msg_id=i
            ),
        )
        for i in (2, 3)
    ]
    tg.add(
        group,
        [
            *anchors,
            message(
                group,
                4,
                "album comment",
                reply_to=types.MessageReplyHeader(reply_to_msg_id=3, reply_to_top_id=2),
            ),
        ],
    )
    tg.full[utils.get_peer_id(source)].linked_chat_id = 11
    initialize(tg, tmp_path)
    result = call(tg, tmp_path, "sync", "channel:10")
    assert result["sync"]["reply_flattened"] == 0
    assert tg.sent[-1].reply_to.reply_to_msg_id == 3
    assert tg.sent[-1].reply_to.top_msg_id == 2


def test_init_preview_counts_discussion_missing_after_interruption(tmp_path):
    source, group = channel(broadcast=True), channel(11, megagroup=True)
    tg = Telegram(source)
    tg.add(group)
    tg.full[utils.get_peer_id(source)].linked_chat_id = 11
    assert call(tg, tmp_path, "init", "channel:10")["peers_to_create"] == 2
    initialize(tg, tmp_path)
    assert call(tg, tmp_path, "init", "channel:10")["peers_to_create"] == 0
    with Store(tmp_path) as store:
        clone = store.all()[0]
        clone.discussion_destination_peer_id = None
        clone.discussion_linked = False
        clone.save()
    assert call(tg, tmp_path, "init", "channel:10")["peers_to_create"] == 1
