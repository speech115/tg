import asyncio
import hashlib
import json
import sqlite3
from types import SimpleNamespace as NS

import pytest
from telethon import errors
from telethon.tl import functions, types

from tg.clone import Store
from tg.clone.__main__ import export, status
from tg.clone.publish import submit
from tg.clone.reupload import download_for_reupload, media_key, resume_offset
from tg.clone.support import PolicyError
from tg.clone.transfer import CHUNK_SIZE, upload_parts

from .fake import Telegram, channel, document, message


def test_mapping_cursor_and_outcomes_commit_together(tmp_path):
    with Store(tmp_path) as store:
        clone = store.create(99, 10, "Source", "broadcast")
        clone.prepare("id_map", [2, 3], "test", "forwarded", {})
        clone.confirm([20, 21])
        store.conn.execute(
            "CREATE TRIGGER fail_metadata BEFORE UPDATE ON clones "
            "BEGIN SELECT RAISE(ABORT, 'disk failure'); END"
        )
        with pytest.raises(sqlite3.IntegrityError):
            clone.finish_pending()
        fresh = store.load(clone.clone_id)
        assert fresh.cursor == 0 and len(fresh.id_map) == 0
        assert store.pending(clone.clone_id)["destination_ids"] == [20, 21]
        store.conn.execute("DROP TRIGGER fail_metadata")
        assert fresh.finish_pending()
        assert fresh.cursor == 3 and dict(fresh.id_map) == {"2": 20, "3": 21}
        assert len(export(store, clone.clone_id)["outcomes"]) == 2


@pytest.mark.parametrize("receipt", ["missing", "duplicate", "extra", "wrong"])
def test_album_rejects_unproven_receipts(tmp_path, receipt):
    with Store(tmp_path) as store:
        clone = store.create(99, 10, "Source", "broadcast")

        async def fake(request):
            a, b = request.random_id
            pairs = {
                "missing": [(a, 20)],
                "duplicate": [(a, 20), (b, 20)],
                "extra": [(a, 20), (b, 21), (1234, 22)],
                "wrong": [(a, 20), (1234, 21)],
            }[receipt]
            return NS(updates=[types.UpdateMessageID(random_id=r, id=i) for r, i in pairs])

        request = functions.messages.ForwardMessagesRequest(
            types.InputPeerSelf(), [2, 3], [0, 0], types.InputPeerSelf()
        )
        with pytest.raises(PolicyError, match="complete cloned batch"):
            asyncio.run(submit(fake, clone, "id_map", [2, 3], request, {}, "forwarded"))
        assert store.pending(clone.clone_id) and clone.cursor == 0 and (not clone.id_map)


def test_changed_source_and_duplicate_random_id_do_not_allocate_new_intentions(tmp_path):
    with Store(tmp_path) as store:
        clone = store.create(99, 10, "Source", "broadcast")
        before = clone.prepare("id_map", [2], "original", "forwarded", {})
        assert clone.prepare("id_map", [2], "original", "forwarded", {}) == before
        with pytest.raises(PolicyError, match="differs"):
            clone.prepare("id_map", [2], "edited", "forwarded", {})
        store.rejected(clone.clone_id, "known rejection")

        async def duplicate(request):
            raise errors.RandomIdDuplicateError(request)

        request = functions.messages.SendMessageRequest(types.InputPeerSelf(), "text", random_id=0)
        with pytest.raises(PolicyError, match="already saw"):
            asyncio.run(submit(duplicate, clone, "id_map", [2], request, {}, "reused"))
        assert store.pending(clone.clone_id)["random_ids"] == [request.random_id]


def test_cache_identity_includes_peer_and_replaced_media(tmp_path):
    source = channel(broadcast=True)
    original = message(source, 2, media=document(100))
    tg = Telegram(source)
    with Store(tmp_path) as store:
        store.create(99, 10, "Source", "broadcast")
        cache = tmp_path / "media"
        first = asyncio.run(download_for_reupload(tg, original, cache))
        assert first.read_bytes() == bytes([100]) * 16
        assert asyncio.run(download_for_reupload(tg, original, cache)) == first
        assert len(tg.downloads) == 1
        replacement = message(source, 2, media=document(101))
        second = asyncio.run(download_for_reupload(tg, replacement, cache))
        assert second != first and second.read_bytes() == bytes([101]) * 16
        same_id_other_peer = message(types.PeerChat(10), 2, media=document(100))
        third = asyncio.run(download_for_reupload(tg, same_id_other_peer, cache))
        assert third != first and third.read_bytes() == first.read_bytes()


def test_interrupted_download_resumes_only_checkpointed_bytes(tmp_path):
    source = channel(broadcast=True)
    original = message(source, 2, media=document(100, size=2 * CHUNK_SIZE + 17))

    class Interrupted(Telegram):
        interrupted = False

        async def iter_download(self, media, **kwargs):
            async for chunk in super().iter_download(media, **kwargs):
                yield chunk
                if not self.interrupted:
                    self.interrupted = True
                    raise OSError("download disconnected")

    tg = Interrupted(source)
    with Store(tmp_path) as store:
        store.create(99, 10, "Source", "broadcast")
        cache = tmp_path / "media"
        with pytest.raises(OSError):
            asyncio.run(download_for_reupload(tg, original, cache))
        result = asyncio.run(download_for_reupload(tg, original, cache))
        assert tg.downloads == [(100, 0), (100, CHUNK_SIZE)]
        assert result.read_bytes() == bytes([100]) * (2 * CHUNK_SIZE + 17)
        identity = media_key(original)
        part = cache / "unproven.part"
        part.write_bytes(b"bad" * 8)
        assert resume_offset(part, identity) == 0
        part.with_suffix(".offset").write_text(json.dumps({"identity": identity, "offset": 16}))
        assert resume_offset(part, identity) == 16 and part.stat().st_size == 16


def test_offline_store_and_account_lock_do_not_touch_auth(tmp_path):
    root = tmp_path / "absent"
    with Store(root, readonly=True) as store:
        assert status(store) == []
    assert not root.exists()
    with Store(root) as first, Store(root) as second, first.lock(99):
        with pytest.raises(PolicyError, match="another clone operation"):
            with second.lock(99):
                pass
        with second.lock(100):
            pass
    with Store(root) as store:
        clone = store.create(99, 10, "Source", "broadcast")
        store.conn.execute(
            "UPDATE clones SET data=? WHERE id=?", ('{"cursor": -1}', clone.clone_id)
        )
        store.conn.commit()
        with pytest.raises(PolicyError, match="invalid clone state"):
            store.load(clone.clone_id)


def test_parallel_upload_reassembles_all_bytes_and_cancels_siblings(tmp_path):
    data = bytes(range(256)) * 8192
    path = tmp_path / "upload.bin"
    path.write_bytes(data)
    tg = Telegram(channel(broadcast=True))
    uploaded = asyncio.run(upload_parts(tg, path))
    assert b"".join(tg.uploads[key] for key in sorted(tg.uploads)) == data
    assert uploaded.md5_checksum == hashlib.md5(data).hexdigest()

    class Failed:
        running = 0
        completed = []

        async def __call__(self, request):
            self.running += 1
            try:
                if request.file_part == 0:
                    await asyncio.sleep(0)
                    raise errors.FloodWaitError(request, capture=10)
                await asyncio.sleep(10)
                self.completed.append(request.file_part)
            finally:
                self.running -= 1

    fake = Failed()
    with pytest.raises(errors.FloodWaitError):
        asyncio.run(upload_parts(fake, path))
    assert fake.running == 0 and fake.completed == []


def test_message_mappings_are_immutable_but_avatar_updates_are_allowed(tmp_path):
    with Store(tmp_path) as store:
        clone = store.create(99, 10, "Source", "broadcast")
        clone.record_mapping(2, 20)
        clone.save()
        with pytest.raises(PolicyError, match="already maps"):
            clone.record_mapping(2, 21)
        assert clone.dest_for(2) == 20
        clone.record_avatar(10, 777)
        clone.record_avatar(11, 777)
        clone.record_avatar(10, 888)
        clone.save()
        assert clone.avatar_for(10) == 888 and clone.avatar_for(11) == 777


def test_interrupted_schema_creation_rolls_back(tmp_path, monkeypatch):
    from tg.clone import state

    schema = state.SCHEMA
    monkeypatch.setattr(state, "SCHEMA", "CREATE TABLE stray (id INTEGER); INVALID SQL;")
    with pytest.raises(sqlite3.OperationalError):
        with Store(tmp_path):
            pass
    monkeypatch.setattr(state, "SCHEMA", schema)
    with Store(tmp_path) as store:
        assert (
            store.conn.execute("SELECT name FROM sqlite_master WHERE name='stray'").fetchone()
            is None
        )
        assert store.create(99, 10, "Source", "broadcast").cursor == 0
