"""The harness API is ordinary Python; no argv, login or extra connection."""

import asyncio
import importlib

import pytest
from telethon import errors
from telethon.tl import functions, types

from tg.clone import Store, replies
from tg.clone.support import PolicyError, RateLimitError

from .fake import Telegram, channel, document, message
from .test_workflow import call, initialize


def invoke(client, root, source="channel:10", **options):
    entry = getattr(importlib.import_module("tg.clone"), "clone", None)
    assert callable(entry), "tg.clone must expose a direct Python clone() coroutine"
    return asyncio.run(entry(client, source, state_root=root, **options))


def test_python_preview_does_not_create_peers_or_send(tmp_path, capsys):
    source = channel(broadcast=True)
    client = Telegram(source, [message(source, 2)])
    result = invoke(client, tmp_path)
    assert result["clone"]["commit_required"]
    assert not client.sent
    assert not any(isinstance(req, functions.channels.CreateChannelRequest) for req in client.calls)
    assert capsys.readouterr().out == ""


def test_python_commit_and_resume_preserve_complete_albums(tmp_path):
    source = channel(broadcast=True)
    client = Telegram(
        source,
        [
            message(source, 2, media=document(100), grouped_id=123),
            message(source, 3, media=document(101), grouped_id=123),
            message(source, 4, reply_to=types.MessageReplyHeader(reply_to_msg_id=2)),
        ],
    )
    first = invoke(client, tmp_path, commit=True, limit=1)
    assert first["sync"]["copied"] == 2
    assert first["sync"]["cursor"] == 3
    assert first["remaining"]
    before = len(client.calls)
    second = invoke(client, tmp_path, commit=True)
    assert second["sync"]["copied"] == 1
    assert not second["remaining"]
    assert client.sent[-1].reply_to.reply_to_msg_id == 2
    assert not any(
        isinstance(
            req,
            (
                functions.channels.CreateChannelRequest,
                functions.account.UpdateNotifySettingsRequest,
                functions.messages.UpdateDialogFilterRequest,
            ),
        )
        for req in client.calls[before:]
    )
    assert invoke(client, tmp_path, commit=True)["sync"]["copied"] == 0


def test_python_resume_recovers_an_unconfirmed_send(tmp_path):
    source = channel(broadcast=True)
    client = Telegram(source, [message(source, 2)])
    client.fail_send = "before"
    with pytest.raises(OSError):
        invoke(client, tmp_path, commit=True)
    with Store(tmp_path, readonly=True) as store:
        saved = store.all()[0]
        intention = store.pending(saved.clone_id)["random_ids"]
    result = invoke(client, tmp_path, commit=True)
    assert result["sync"]["copied"] == 1
    assert client.sent[0].random_id == intention
    assert len(client.sent) == 1


@pytest.mark.parametrize(
    "options",
    [
        {"limit": 0},
        {"limit": -1},
        {"limit": True},
        {"limit": 1.5},
        {"max_runtime": 0},
        {"max_runtime": float("nan")},
        {"max_runtime": float("inf")},
    ],
)
def test_python_invalid_caps_fail_before_telegram(tmp_path, options):
    source = channel(broadcast=True)
    client = Telegram(source, [])
    with pytest.raises(PolicyError):
        invoke(client, tmp_path, commit=True, **options)
    assert client.calls == []


def test_python_entry_keeps_persisted_cooldown(tmp_path):
    source = channel(broadcast=True)

    class Flooded(Telegram):
        def publish(self, request):
            raise errors.FloodWaitError(request, capture=30)

    client = Flooded(source, [message(source, 2)])
    initialize(client, tmp_path)
    with pytest.raises(RateLimitError):
        invoke(client, tmp_path, commit=True)
    assert client.flood_sleep_threshold == 60
    count = len(client.calls)
    with pytest.raises(RateLimitError):
        invoke(client, tmp_path, commit=True)
    assert len(client.calls) == count


def test_each_batch_is_classified_once(tmp_path, monkeypatch):
    source = channel(broadcast=True)
    client = Telegram(
        source,
        [
            message(source, 2),
            message(source, 3, reply_to=types.MessageReplyHeader(reply_to_msg_id=2)),
        ],
    )
    initialize(client, tmp_path)
    calls = []
    original = replies.target

    def counted(messages, *args, **kwargs):
        calls.append(tuple(item.id for item in messages))
        return original(messages, *args, **kwargs)

    monkeypatch.setattr(replies, "target", counted)
    result = call(client, tmp_path, "sync", "channel:10")
    assert result["sync"]["copied"] == 2
    assert calls == [(2,), (3,)]


def test_comments_share_the_same_single_classification_plan(tmp_path, monkeypatch):
    from telethon import utils

    from .fake import NOW

    source, group = channel(broadcast=True), channel(11, megagroup=True)
    client = Telegram(source, [message(source, 2)])
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
    initialize(client, tmp_path)
    calls, target = [], replies.target

    def counted(messages, *args, **kwargs):
        calls.append(tuple(item.id for item in messages))
        return target(messages, *args, **kwargs)

    monkeypatch.setattr(replies, "target", counted)
    result = invoke(client, tmp_path, commit=True)
    assert result["sync"]["copied"] == 2
    assert result["sync"]["discussion_cursor"] == 6
    assert client.sent[-1].reply_to.reply_to_msg_id == 2
    assert calls == [(2,), (6,)]


@pytest.mark.parametrize("kind", ["broadcast", "megagroup", "forum", "basic", "dialog", "bot"])
def test_direct_api_keeps_all_source_types(tmp_path, kind):
    from .fake import NOW

    if kind in {"dialog", "bot"}:
        source = types.User(10, first_name="Person", bot=kind == "bot", access_hash=1)
        ref = "user:10"
    elif kind == "basic":
        source = types.Chat(10, "Basic", types.ChatPhotoEmpty(), 1, NOW, 1)
        ref = "chat:10"
    else:
        source = channel(
            broadcast=kind == "broadcast", megagroup=kind != "broadcast", forum=kind == "forum"
        )
        ref = "channel:10"
    client = Telegram(source, [message(source, 2)])
    result = invoke(client, tmp_path, ref, commit=True)
    assert result["sync"]["copied"] == 1
    assert invoke(client, tmp_path, ref, commit=True)["sync"]["copied"] == 0


def test_incomplete_initialization_is_adopted_not_recreated(tmp_path, monkeypatch):
    from tg.clone import init_peers

    source = channel(broadcast=True)
    client = Telegram(source, [message(source, 2)])
    original = init_peers.copy_profile

    async def interrupted(*args):
        raise OSError("interrupted after destination was recorded")

    monkeypatch.setattr(init_peers, "copy_profile", interrupted)
    with pytest.raises(OSError):
        invoke(client, tmp_path, commit=True)
    with Store(tmp_path, readonly=True) as store:
        saved = store.all()[0]
        assert saved.destination_peer_id is not None
        assert not saved.initialized
    monkeypatch.setattr(init_peers, "copy_profile", original)
    assert invoke(client, tmp_path, commit=True)["sync"]["copied"] == 1
    creates = [r for r in client.calls if isinstance(r, functions.channels.CreateChannelRequest)]
    assert len(creates) == 1


def test_old_metadata_without_initialization_flag_resumes(tmp_path):
    import json

    source = channel(broadcast=True)
    client = Telegram(source, [message(source, 2)])
    first = invoke(client, tmp_path, commit=True)
    with Store(tmp_path) as store:
        saved = store.all()[0]
        metadata = saved.metadata()
        metadata.pop("initialized")
        store.conn.execute(
            "UPDATE clones SET data=? WHERE id=?", (json.dumps(metadata), saved.clone_id)
        )
        store.conn.commit()
    second = invoke(client, tmp_path, commit=True)
    assert second["sync"]["copied"] == 0
    assert first["clone"]["destination"]["id"] == second["clone"]["destination"]["id"]
    assert (
        len([r for r in client.calls if isinstance(r, functions.channels.CreateChannelRequest)])
        == 1
    )
    with Store(tmp_path, readonly=True) as store:
        saved = store.all()[0]
        assert saved.initialized and saved.progress["transport"] == "forwarded"


@pytest.mark.parametrize("value", ["yes", 1, None])
def test_commit_requires_an_explicit_boolean(tmp_path, value):
    source = channel(broadcast=True)
    client = Telegram(source, [])
    with pytest.raises(PolicyError, match="booleans"):
        invoke(client, tmp_path, commit=value)
    assert not client.calls


def test_typed_resolution_does_not_scan_other_clone_metadata(tmp_path, monkeypatch):
    from tg.clone import engine

    source = channel(broadcast=True)
    client = Telegram(source, [])
    with Store(tmp_path) as store:

        def unrelated_state():
            raise AssertionError("a typed peer does not require an alias search")

        monkeypatch.setattr(store, "all", unrelated_state)
        resolved, kind, _ = asyncio.run(
            engine._resolve_source(client, store, "channel:10", account_user_id=client.me.id)
        )
        assert resolved is source and kind == "broadcast"
