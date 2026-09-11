import asyncio
import json
from types import SimpleNamespace as NS

import pytest
from telethon import errors, utils
from telethon.tl import functions, types

from tg.clone import Store, run
from tg.clone.__main__ import export, status
from tg.clone.state import CloneState
from tg.clone.support import PolicyError, RateLimitError

from .fake import NOW, Telegram, channel, document, message


def call(tg, root, *args):
    return asyncio.run(run(tg, list(args), state_root=root))


def initialize(tg, root, source="channel:10", *options):
    preview = call(tg, root, "init", source, *options)
    return call(tg, root, "init", source, "--commit", preview["preview_id"])


@pytest.mark.parametrize("kind", ["broadcast", "megagroup", "forum", "basic", "dialog", "bot"])
def test_initialize_copy_resume_all_source_kinds(tmp_path, kind):
    if kind in {"dialog", "bot"}:
        source = types.User(10, first_name="Person", bot=kind == "bot", access_hash=1)
    elif kind == "basic":
        source = types.Chat(10, "Basic", types.ChatPhotoEmpty(), 1, NOW, 1)
    else:
        source = channel(
            broadcast=kind == "broadcast", megagroup=kind != "broadcast", forum=kind == "forum"
        )
    peer_type = "user" if kind in {"dialog", "bot"} else "chat" if kind == "basic" else "channel"
    ref = f"{peer_type}:10"
    history = [
        message(source, 2),
        message(source, 3, media=document(100), grouped_id=123),
        message(source, 4, media=document(101), grouped_id=123),
        message(
            source,
            5,
            "😀 reply",
            media=document(102),
            entities=[types.MessageEntityBold(3, 5)],
            reply_to=types.MessageReplyHeader(reply_to_msg_id=2),
        ),
    ]
    tg = Telegram(source, history)
    tg.full[utils.get_peer_id(source)].pinned_msg_id = 2
    preview = call(tg, tmp_path, "init", ref)
    assert not any(isinstance(req, functions.channels.CreateChannelRequest) for req in tg.calls)
    created = call(tg, tmp_path, "init", ref, "--commit", preview["preview_id"])
    destination = tg.entities[
        utils.get_peer_id(types.PeerChannel(created["clone"]["destination"]["id"]))
    ]
    assert destination.creator and (not destination.username)
    assert created["ergonomics"] == {"muted": True, "folder": "added"}
    first = call(tg, tmp_path, "sync", ref, "--limit", "2")
    assert first["sync"]["copied"] == 3 and first["sync"]["cursor"] == 4
    assert first["remaining"] and tg.participants == [] and (tg.downloads == [])
    second = call(tg, tmp_path, "sync", ref)
    assert second["sync"]["copied"] == 1 and (not second["remaining"])
    assert second["sync"]["reused"] == 1
    sent = tg.sent[-1]
    assert isinstance(sent, functions.messages.SendMediaRequest)
    assert sent.reply_to.reply_to_msg_id == 2
    assert isinstance(sent.media, types.InputMediaDocument)
    assert sent.entities[-1].offset >= 3 and sent.entities[-1].length == 5
    assert len(tg.participants) == 1
    assert call(tg, tmp_path, "sync", ref)["sync"]["copied"] == 0
    assert len(tg.participants) == 1
    call(tg, tmp_path, "roster", ref)
    assert len(tg.participants) == 2
    with Store(tmp_path, readonly=True) as store:
        [saved] = status(store, ref)
        assert saved["mapped"]["posts"] == 4
        assert saved["progress"]["status"] == "complete"
        assert len(export(store, ref)["id_map"]) == 4


def test_interruption_reuses_intention_and_recovers_confirmed_receipt(tmp_path, monkeypatch):
    source = channel(broadcast=True)
    tg = Telegram(source, [message(source, 2), message(source, 3)])
    initialize(tg, tmp_path)
    tg.fail_send = "before"
    with pytest.raises(OSError):
        call(tg, tmp_path, "sync", "channel:10")
    with Store(tmp_path, readonly=True) as store:
        [row] = status(store)
        random_ids = row["pending"]["random_ids"]
        assert row["mapped"]["posts"] == 0
        assert row["progress"]["status"] == "stopped"
    finish = CloneState.finish_pending

    def fail_after_receipt(clone):
        pending = clone.store.pending(clone.clone_id)
        if pending and pending.get("destination_ids"):
            raise OSError("disk failed before mapping commit")
        return finish(clone)

    monkeypatch.setattr(CloneState, "finish_pending", fail_after_receipt)
    with pytest.raises(OSError):
        call(tg, tmp_path, "sync", "channel:10")
    assert tg.sent[0].random_id == random_ids
    monkeypatch.setattr(CloneState, "finish_pending", finish)
    result = call(tg, tmp_path, "sync", "channel:10")
    assert result["sync"]["copied"] == 1
    assert len(tg.sent) == 2
    with Store(tmp_path, readonly=True) as store:
        [row] = status(store)
        assert row["mapped"]["posts"] == 2 and row["pending"] is None


def test_unknown_delivery_stops_before_sending_again(tmp_path):
    source = channel(broadcast=True)
    tg = Telegram(source, [message(source, 2)])
    initialize(tg, tmp_path)
    tg.fail_send = "after"
    with pytest.raises(OSError):
        call(tg, tmp_path, "sync", "channel:10")
    with pytest.raises(PolicyError, match="unexpected tail"):
        call(tg, tmp_path, "sync", "channel:10")
    assert len(tg.sent) == 1
    with Store(tmp_path, readonly=True) as store:
        assert status(store)[0]["pending"] is not None


def test_protected_upload_attributes_and_spoiler(tmp_path):
    source = channel(broadcast=True, noforwards=True)
    tg = Telegram(source, [message(source, 2, media=document(spoiler=True))])
    initialize(tg, tmp_path)
    result = call(tg, tmp_path, "sync", "channel:10")
    assert result["sync"]["reuploaded"] == 1
    media = tg.sent[-1].media
    assert isinstance(media, types.InputMediaUploadedDocument)
    assert media.spoiler and media.mime_type == "audio/ogg"
    assert media.attributes[0].voice and media.attributes[0].duration == 12
    assert list(tg.uploads.values()) == [bytes([100]) * 16]
    assert not list((tmp_path / "media").glob("*"))


def test_forum_topics_and_reply_placement(tmp_path):
    source = channel(megagroup=True, forum=True)
    tg = Telegram(
        source,
        [
            message(source, 7, action=types.MessageActionTopicCreate("Topic", 123)),
            message(
                source, 8, reply_to=types.MessageReplyHeader(reply_to_msg_id=7, forum_topic=True)
            ),
            message(
                source,
                9,
                media=document(),
                reply_to=types.MessageReplyHeader(
                    reply_to_msg_id=8, reply_to_top_id=7, forum_topic=True
                ),
            ),
        ],
    )
    created = initialize(tg, tmp_path)
    assert tg.entities[
        utils.get_peer_id(types.PeerChannel(created["clone"]["destination"]["id"]))
    ].forum
    result = call(tg, tmp_path, "sync", "channel:10")
    assert result["sync"]["topics_created"] == 1
    assert result["sync"]["copied"] == 2
    assert tg.sent[-1].reply_to.reply_to_msg_id == 3
    assert tg.sent[-1].reply_to.top_msg_id == 2
    assert call(tg, tmp_path, "sync", "channel:10")["sync"]["copied"] == 0


def test_comments_interleave_and_resume_dependencies(tmp_path, monkeypatch):
    from tg.clone import engine

    monkeypatch.setattr(engine, "WINDOW", 1)
    source = channel(broadcast=True)
    group = channel(11, megagroup=True)
    tg = Telegram(source, [message(source, 2), message(source, 3), message(source, 4)])
    tg.add(
        group,
        [
            message(
                group,
                1,
                fwd_from=types.MessageFwdHeader(
                    date=NOW, saved_from_peer=types.PeerChannel(10), saved_from_msg_id=2
                ),
            ),
            message(group, 2, "comment", reply_to=types.MessageReplyHeader(reply_to_msg_id=1)),
            message(
                group,
                3,
                "later",
                reply_to=types.MessageReplyHeader(
                    reply_to_msg_id=4, reply_to_peer_id=types.PeerChannel(10)
                ),
            ),
        ],
    )
    tg.full[utils.get_peer_id(source)].linked_chat_id = group.id
    result = initialize(tg, tmp_path)
    assert result["clone"]["comments"] == "enabled"
    first = call(tg, tmp_path, "sync", "channel:10", "--limit", "2")
    assert first["sync"]["cursor"] == 2 and first["sync"]["discussion_cursor"] == 2
    assert first["remaining"]
    result = call(tg, tmp_path, "sync", "channel:10")
    assert result["sync"]["copied"] == 3 and result["sync"]["discussion_cursor"] == 3
    assert not result["remaining"]
    assert tg.sent[-1].reply_to.reply_to_msg_id > 1
    with Store(tmp_path, readonly=True) as store:
        [row] = status(store)
        assert row["mapped"] == {"posts": 3, "comments": 2, "topics": 0}


def test_poll_default_readonly_and_durable_vote_retraction(tmp_path):
    from tg.clone import snapshot

    poll = types.MessageMediaPoll(
        types.Poll(
            1,
            types.TextWithEntities("Question", []),
            [
                types.PollAnswer(types.TextWithEntities("Yes", []), b"1"),
                types.PollAnswer(types.TextWithEntities("No", []), b"2"),
            ],
            hash=1,
        ),
        types.PollResults(total_voters=2),
    )
    source = channel(broadcast=True)
    tg = Telegram(source, [message(source, 2, media=poll)])
    initialize(tg, tmp_path)
    call(tg, tmp_path, "sync", "channel:10")
    assert snapshot.BREAKDOWN_UNAVAILABLE in tg.sent[-1].message
    assert not any(isinstance(req, functions.messages.SendVoteRequest) for req in tg.calls)

    class Voter:
        def __init__(self):
            self.options, self.fail_retract = ([], True)

        async def __call__(self, request):
            self.options.append(request.options)
            if not request.options and self.fail_retract:
                raise errors.FloodWaitError(request, capture=12)
            return NS(
                updates=[
                    types.UpdateMessagePoll(
                        poll_id=1,
                        results=types.PollResults(
                            total_voters=3,
                            results=[
                                types.PollAnswerVoters(b"1", 2),
                                types.PollAnswerVoters(b"2", 1),
                            ],
                        ),
                    )
                ]
            )

    voter = Voter()
    with Store(tmp_path) as store:
        clone = store.all()[0]
        with pytest.raises(errors.FloodWaitError):
            asyncio.run(
                snapshot.render(
                    voter,
                    tg.history[utils.get_peer_id(source)][0],
                    peer=source,
                    clone_state=clone,
                    capture_poll_votes=True,
                )
            )
        assert store.conn.execute("SELECT count(*) FROM votes").fetchone()[0] == 1
        voter.fail_retract = False
        asyncio.run(snapshot.recover_votes(voter, store, tg.me.id))
        assert voter.options == [[b"1"], [], []]
        assert store.conn.execute("SELECT count(*) FROM votes").fetchone()[0] == 0


def test_floodwait_persists_account_cooldown_and_restores_client(tmp_path):
    source = channel(broadcast=True)

    class Flooded(Telegram):
        def publish(self, request):
            raise errors.FloodWaitError(request, capture=120)

    tg = Flooded(source, [message(source, 2)])
    initialize(tg, tmp_path)
    with pytest.raises(RateLimitError):
        call(tg, tmp_path, "sync", "channel:10")
    assert tg.flood_sleep_threshold == 60
    before = len(tg.calls)
    with pytest.raises(RateLimitError):
        call(tg, tmp_path, "sync", "channel:10")
    assert len(tg.calls) == before
    with Store(tmp_path, readonly=True) as store:
        assert status(store)[0]["progress"]["status"] == "cooldown"


def test_preview_single_use_replace_archives_without_deleting_peer(tmp_path):
    source = channel(broadcast=True)
    tg = Telegram(source, [message(source, 2)])
    original = initialize(tg, tmp_path)
    call(tg, tmp_path, "sync", "channel:10")
    preview = call(tg, tmp_path, "init", "channel:10", "--replace")
    with pytest.raises(PolicyError, match="preview command"):
        call(tg, tmp_path, "init", "channel:10", "--commit", preview["preview_id"], "--replace")
    replaced = call(tg, tmp_path, "init", "channel:10", "--commit", preview["preview_id"])
    assert original["clone"]["destination"]["id"] != replaced["clone"]["destination"]["id"]
    [archive] = list((tmp_path / "archive").glob("*.json"))
    assert len(json.loads(archive.read_text())["id_map"]) == 1
    with pytest.raises(PolicyError, match="already used"):
        call(tg, tmp_path, "init", "channel:10", "--commit", preview["preview_id"])


def test_runtime_cap_finishes_whole_album_then_resumes(tmp_path, monkeypatch):
    from tg.clone import engine

    current = [0.0]
    monkeypatch.setattr(engine.time, "monotonic", lambda: current[0])
    source = channel(broadcast=True)

    class Slow(Telegram):
        def publish(self, request):
            result = super().publish(request)
            current[0] += 10
            return result

    tg = Slow(
        source,
        [
            message(source, 2, media=document(100), grouped_id=123),
            message(source, 3, media=document(101), grouped_id=123),
            message(source, 4),
        ],
    )
    initialize(tg, tmp_path)
    result = call(tg, tmp_path, "sync", "channel:10", "--max-runtime", "1")
    assert result["sync"]["copied"] == 2 and result["sync"]["cursor"] == 3
    assert result["stop_reason"] == "wall_clock_cap" and not tg.participants
    assert call(tg, tmp_path, "sync", "channel:10")["sync"]["copied"] == 1


def test_preview_token_is_a_cli_value_even_when_random_part_starts_with_dash(tmp_path, monkeypatch):
    from tg.clone import state

    monkeypatch.setattr(state.secrets, "token_urlsafe", lambda size: "-random-value")
    tg = Telegram(channel(broadcast=True))
    assert initialize(tg, tmp_path)["clone"]["status"] == "ready"


def test_wrong_account_does_not_consume_preview(tmp_path):
    tg = Telegram(channel(broadcast=True))
    preview = call(tg, tmp_path, "init", "channel:10")
    me = tg.me
    tg.me = types.User(100, access_hash=1)
    with pytest.raises(PolicyError, match="different Telegram account"):
        call(tg, tmp_path, "init", "channel:10", "--commit", preview["preview_id"])
    tg.me = me
    assert (
        call(tg, tmp_path, "init", "channel:10", "--commit", preview["preview_id"])["clone"][
            "status"
        ]
        == "ready"
    )
