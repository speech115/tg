"""Safety checks for the Ponytail reductions in folder and comment handling."""

import asyncio

import pytest
from telethon import errors, utils
from telethon.tl import types

from tg.clone import Store, ergonomics
from tg.clone.support import RateLimitError

from .fake import NOW, Telegram, channel, message
from .test_workflow import call, initialize


def linked_client(client_type=Telegram):
    source, group = channel(10, broadcast=True), channel(11, megagroup=True)
    client = client_type(source, [message(source, 2)])
    client.add(
        group,
        [
            message(
                group,
                5,
                fwd_from=types.MessageFwdHeader(
                    date=NOW, saved_from_peer=types.PeerChannel(10), saved_from_msg_id=2
                ),
            ),
            message(group, 6, "comment", reply_to=types.MessageReplyHeader(reply_to_msg_id=5)),
        ],
    )
    client.full[utils.get_peer_id(source)].linked_chat_id = group.id
    return client


def test_folder_keeps_peer_types_distinct_and_is_idempotent():
    source = channel(10, broadcast=True)
    client = Telegram(source)
    client.filters = [
        types.DialogFilter(
            id=2,
            title=types.TextWithEntities("Clone", []),
            pinned_peers=[],
            include_peers=[types.InputPeerUser(10, 1)],
            exclude_peers=[],
        )
    ]
    assert asyncio.run(ergonomics._ensure_folder(client, [source])) == "added"
    included = client.filters[0].include_peers
    assert [utils.get_peer_id(peer) for peer in included] == [10, -1000000000010]
    assert asyncio.run(ergonomics._ensure_folder(client, [source])) == "present"
    assert client.filters[0].include_peers == included


def test_reader_access_loss_records_degradation(tmp_path):
    class UnreadableDiscussion(Telegram):
        async def iter_messages(self, peer, **kwargs):
            if peer.id == 11:
                raise errors.ChannelPrivateError(None)
            async for item in super().iter_messages(peer, **kwargs):
                yield item

    client = linked_client(UnreadableDiscussion)
    initialize(client, tmp_path)
    result = call(client, tmp_path, "sync", "channel:10")
    assert result["degraded"]
    with Store(tmp_path, readonly=True) as store:
        saved = store.all()[0]
        assert saved.comments == "unavailable"
        assert saved.discussion_cursor == 0


def test_consumer_send_error_does_not_degrade_reader(tmp_path):
    class UnwritableDiscussion(Telegram):
        def publish(self, request):
            peer = getattr(request, "peer", None) or getattr(request, "to_peer", None)
            if peer is not None and utils.get_peer_id(peer) in self.links.values():
                raise errors.ChannelPrivateError(request)
            return super().publish(request)

    client = linked_client(UnwritableDiscussion)
    initialize(client, tmp_path)
    with pytest.raises(errors.ChannelPrivateError):
        call(client, tmp_path, "sync", "channel:10")
    with Store(tmp_path, readonly=True) as store:
        saved = store.all()[0]
        assert saved.comments == "enabled"
        assert saved.discussion_cursor == 5


def test_reader_flood_wait_is_not_mistaken_for_access_loss(tmp_path):
    class FloodedDiscussion(Telegram):
        async def iter_messages(self, peer, **kwargs):
            if peer.id == 11:
                raise errors.FloodWaitError(None, capture=30)
            async for item in super().iter_messages(peer, **kwargs):
                yield item

    client = linked_client(FloodedDiscussion)
    initialize(client, tmp_path)
    with pytest.raises(RateLimitError):
        call(client, tmp_path, "sync", "channel:10")
    with Store(tmp_path, readonly=True) as store:
        saved = store.all()[0]
        assert saved.comments == "enabled"
        assert saved.discussion_cursor == 0
    with pytest.raises(RateLimitError):
        call(client, tmp_path, "sync", "channel:10")
