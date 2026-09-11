"""Explicit Telegram references cannot be shadowed by saved clone titles."""

import asyncio

import pytest
from telethon import utils

from tg.clone import Store, engine
from tg.clone.support import PolicyError

from .fake import Telegram, channel, message
from .test_python_api import invoke
from .test_workflow import call, initialize


class LinkTelegram(Telegram):
    """Use Telethon's public-username/link parser in the in-memory service."""

    async def get_entity(self, peer):
        if isinstance(peer, str):
            username, is_invite = utils.parse_username(peer)
            if username and not is_invite:
                peer = username
        return await super().get_entity(peer)


def shadowed_client(root, reference):
    old = channel(10, broadcast=True, username="old_channel")
    old.title = f"Archive mentioning {reference.strip()}"
    target = channel(20, broadcast=True, username="target_channel")
    target.title = "Requested channel"
    client = LinkTelegram(old, [message(old, 2, "old history")])
    client.add(target, [message(target, 2, "requested history")])
    invoke(client, root, "channel:10", commit=True)
    client.history[utils.get_peer_id(old)].append(message(old, 3, "wrong new post"))
    return client


@pytest.mark.parametrize(
    "reference",
    [
        "@target_channel",
        " @target_channel ",
        "https://t.me/target_channel",
        "http://t.me/target_channel",
        "t.me/target_channel",
        "telegram.me/target_channel",
        "telegram.dog/target_channel",
        "www.t.me/target_channel",
        "www.telegram.me/target_channel",
        "www.telegram.dog/target_channel",
    ],
)
def test_preview_and_commit_use_same_explicit_source(tmp_path, reference):
    client = shadowed_client(tmp_path, reference)
    preview = invoke(client, tmp_path, reference)
    assert preview["clone"]["source"]["id"] == 20
    result = invoke(client, tmp_path, reference, commit=True)
    assert result["clone"]["source"]["id"] == 20
    assert result["sync"]["copied"] == 1
    assert client.sent[-1].from_peer.id == 20
    with Store(tmp_path, readonly=True) as store:
        old = next(c for c in store.all() if c.source_peer_id == 10)
        assert old.cursor == 2 and old.dest_for(3) is None


@pytest.mark.parametrize("reference", ["@target_channel", "https://t.me/target_channel"])
@pytest.mark.parametrize("operation", ["init", "sync", "refresh", "roster"])
def test_argv_operations_use_the_same_explicit_source(tmp_path, reference, operation):
    client = shadowed_client(tmp_path, reference)
    target = initialize(client, tmp_path, "channel:20")
    result = call(client, tmp_path, operation, reference)
    if operation in ("init", "refresh"):
        assert result["clone"]["source"]["id"] == 20
        result = call(client, tmp_path, operation, reference, "--commit", result["preview_id"])
    clone_id = result["clone_id"] if operation == "roster" else result["clone"]["id"]
    assert clone_id == target["clone"]["id"]


@pytest.mark.parametrize(
    "reference", ["@missing_channel", "t.me/missing_channel", "t.me/not!valid"]
)
@pytest.mark.parametrize("commit", [False, True])
def test_unresolved_explicit_source_never_falls_back_to_title(tmp_path, reference, commit):
    client = shadowed_client(tmp_path, reference)
    before = list(client.sent)
    with pytest.raises(PolicyError, match="source not found"):
        invoke(client, tmp_path, reference, commit=commit)
    assert client.sent == before
    with Store(tmp_path, readonly=True) as store:
        assert len(store.all()) == 1 and store.all()[0].cursor == 2


@pytest.mark.parametrize("alias_kind", ["id", "title"])
def test_saved_alias_works_in_preview_and_both_commit_interfaces(tmp_path, alias_kind):
    client = shadowed_client(tmp_path, "@target_channel")
    with Store(tmp_path, readonly=True) as store:
        saved = store.all()[0]
        alias = saved.clone_id if alias_kind == "id" else "Archive mentioning"
    preview = invoke(client, tmp_path, alias)
    assert preview["clone"]["source"]["id"] == 10
    initialized = initialize(client, tmp_path, alias)
    result = invoke(client, tmp_path, alias, commit=True)
    assert initialized["clone"]["id"] == result["clone"]["id"] == saved.clone_id
    assert result["sync"]["copied"] == 1


@pytest.mark.parametrize("commit", [False, True])
def test_ambiguous_saved_alias_is_rejected_in_preview_and_commit(tmp_path, commit):
    client = shadowed_client(tmp_path, "@target_channel")
    client.entities[-1000000000020].title = "Archive mentioning another channel"
    initialize(client, tmp_path, "channel:20")
    before = list(client.sent)
    with pytest.raises(PolicyError, match="multiple clones"):
        invoke(client, tmp_path, "Archive mentioning", commit=commit)
    assert client.sent == before


def test_explicit_reference_does_not_scan_saved_aliases(tmp_path, monkeypatch):
    client = shadowed_client(tmp_path, "@target_channel")
    with Store(tmp_path) as store:

        def unexpected_scan():
            raise AssertionError("explicit references must not search saved titles")

        monkeypatch.setattr(store, "all", unexpected_scan)
        resolved, _, _ = asyncio.run(
            engine._resolve_source(client, store, "@target_channel", account_user_id=client.me.id)
        )
        assert resolved.id == 20
