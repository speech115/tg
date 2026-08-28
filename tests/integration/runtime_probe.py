"""Exercise the public ``tg`` boundary against a real Telegram session.

The default mode is read-only. Other modes exercise the process runtime and are
selected with ``TG_PROBE_MODE``.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

from telethon import errors

# ``tg`` injects these names into the script namespace.
client = globals()["client"]
functions = globals()["functions"]
types = globals()["types"]


async def safe_probe() -> None:
    assert client.is_connected()
    assert client.flood_sleep_threshold > 0
    print(f"connection=ok flood_sleep_threshold={client.flood_sleep_threshold}")

    me = await client.get_me()
    assert me is not None and me.id
    print(f"identity=ok id={me.id}")

    dialogs = await client.get_dialogs(limit=10)
    assert len(dialogs) <= 10
    print(f"dialogs=ok count={len(dialogs)}")

    messages = await client.get_messages("me", limit=200)
    assert len(messages) <= 200
    print(f"messages=ok count={len(messages)}")

    search_term = os.environ.get("TG_PROBE_SEARCH", "tg").strip() or "tg"
    search_results = await client.get_messages("me", search=search_term, limit=3)
    assert len(search_results) <= 3
    print(f"search=ok results={len(search_results)}")

    full_user = await client(functions.users.GetFullUserRequest(id=types.InputUserSelf()))
    assert full_user.users and full_user.users[0].id == me.id
    print("raw_tl=ok")

    max_media_bytes = int(os.environ.get("TG_PROBE_MAX_MEDIA_BYTES", "10000000"))
    media = next(
        (
            message
            for message in messages
            if message
            and (message.photo or message.document)
            and (
                message.file is None
                or message.file.size is None
                or message.file.size <= max_media_bytes
            )
        ),
        None,
    )
    if media is None:
        print("download=skip:no-small-photo-or-document")
    else:
        with tempfile.TemporaryDirectory(prefix="tg-boundary-") as directory:
            output = await client.download_media(media, file=str(Path(directory) / "media"))
            assert output is not None
            artifact = Path(output)
            assert artifact.is_file() and artifact.stat().st_size > 0
            print(f"download=ok bytes={artifact.stat().st_size}")

    cycles = int(os.environ.get("TG_PROBE_LOOP_CYCLES", "10000"))
    assert cycles > 0
    visited = 0
    for _ in range(cycles):
        for message in messages:
            visited += message.id is not None
    print(f"loop=ok cycles={cycles} visited={visited}")

    try:
        await asyncio.wait_for(asyncio.sleep(0.05), timeout=0.001)
    except TimeoutError:
        print("timeout=ok")
    else:
        raise AssertionError("timeout probe completed without timing out")

    try:
        raise errors.FloodWaitError(request=None, capture=1)
    except errors.FloodWaitError as exc:
        assert exc.seconds == 1
        print("floodwait=handled synthetic_seconds=1")


async def main() -> None:
    mode = os.environ.get("TG_PROBE_MODE", "safe")
    if mode == "safe":
        await safe_probe()
    elif mode == "floodwait":
        raise errors.FloodWaitError(request=None, capture=1)
    elif mode == "exception":
        raise RuntimeError("boundary exception")
    elif mode == "hang":
        print("hang=started", flush=True)
        await asyncio.Event().wait()
    else:
        raise ValueError(f"unknown TG_PROBE_MODE: {mode}")


await main()  # noqa: F704
