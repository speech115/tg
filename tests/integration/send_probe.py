"""Exercise send and retry semantics through the public ``tg`` boundary.

This probe mutates only the explicit target and removes its uniquely marked
test messages before it exits.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import tempfile
import uuid
from pathlib import Path

# ``tg`` injects these names into the script namespace.
client = globals()["client"]
functions = globals()["functions"]


async def find_marker_ids(target: str, marker: str, search: str) -> list[int]:
    for attempt in range(6):
        messages = await client.get_messages(target, search=search, limit=20)
        ids = [message.id for message in messages if message.raw_text == marker]
        if ids or attempt == 5:
            return ids
        await asyncio.sleep(0.2)


def raw_message(peer: object, text: str, random_id: int) -> object:
    return functions.messages.SendMessageRequest(
        peer=peer,
        message=text,
        random_id=random_id,
    )


async def drop_one_response(request: object) -> None:
    original_call = client._call
    dropped = False

    async def call_drop(
        sender: object,
        request_: object,
        ordered: bool = False,
        flood_sleep_threshold: int | None = None,
    ) -> object:
        nonlocal dropped
        result = await original_call(
            sender,
            request_,
            ordered=ordered,
            flood_sleep_threshold=flood_sleep_threshold,
        )
        if not dropped:
            dropped = True
            raise TimeoutError("simulated response loss after Telegram acceptance")
        return result

    client._call = call_drop
    try:
        await client(request)
    finally:
        client._call = original_call
    assert dropped


async def send_probe() -> None:
    target = os.environ.get("TG_SEND_PROBE_TARGET")
    if not target:
        raise ValueError("set TG_SEND_PROBE_TARGET explicitly, for example: me")
    assert client.is_connected()

    token = uuid.uuid4().hex
    plain_marker = f"tg-send-probe-{token}-plain"
    file_marker = f"tg-send-probe-{token}-file"
    dedup_marker = f"tg-send-probe-{token}-dedup"
    uncertain_marker = f"tg-send-probe-{token}-uncertain"
    markers = [plain_marker, file_marker, dedup_marker, uncertain_marker]

    try:
        plain = await client.send_message(target, plain_marker)
        assert plain is not None and plain.id
        print("send_text=ok")

        with tempfile.TemporaryDirectory(prefix="tg-send-boundary-") as directory:
            file_path = Path(directory) / "payload.txt"
            file_path.write_text(f"{file_marker}\n", encoding="utf-8")
            file_message = await client.send_file(target, str(file_path), caption=file_marker)
        if isinstance(file_message, list):
            assert len(file_message) == 1
            file_message = file_message[0]
        assert file_message is not None and file_message.id
        print("send_file=ok")

        peer = await client.get_input_entity(target)
        dedup_id = secrets.randbits(63)
        await client(raw_message(peer, dedup_marker, dedup_id))
        await client(raw_message(peer, dedup_marker, dedup_id))
        dedup_ids = await find_marker_ids(target, dedup_marker, token)
        assert len(dedup_ids) == 1, dedup_ids
        print("random_id=deduplicated count=1")

        uncertain_id = secrets.randbits(63)
        uncertain_request = raw_message(peer, uncertain_marker, uncertain_id)
        try:
            await drop_one_response(uncertain_request)
        except TimeoutError:
            print("uncertain_response=simulated-timeout-after-acceptance")
        else:
            raise AssertionError("response-drop simulation did not time out")

        await client(raw_message(peer, uncertain_marker, uncertain_id))
        uncertain_ids = await find_marker_ids(target, uncertain_marker, token)
        assert len(uncertain_ids) == 1, uncertain_ids
        print("uncertain_retry=deduplicated count=1")
    finally:
        ids = {
            message_id
            for marker in markers
            for message_id in await find_marker_ids(target, marker, token)
        }
        if ids:
            await client.delete_messages(target, list(ids))
        print(f"cleanup=ok messages={len(ids)}")


await send_probe()  # noqa: F704
