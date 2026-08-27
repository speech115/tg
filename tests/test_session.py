import asyncio
from pathlib import Path

import pytest

from tg.config import Config
from tg.errors import SessionBusyError
from tg.session import client_for, session_lock


def test_session_lock_raises_typed_error(tmp_path: Path, monkeypatch) -> None:
    import tg.session

    def fail_lock(_fd: int, _operation: int) -> None:
        raise BlockingIOError

    monkeypatch.setattr(tg.session.fcntl, "flock", fail_lock)

    with pytest.raises(SessionBusyError, match="session is busy"):
        with session_lock(tmp_path / "main"):
            pass


def test_client_for_leaves_flood_wait_default_to_telethon(tmp_path: Path, monkeypatch) -> None:
    import tg.session

    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, *_args: object, **kwargs: object) -> None:
            captured.update(kwargs)

        async def connect(self) -> None:
            return None

        async def is_user_authorized(self) -> bool:
            return True

        async def disconnect(self) -> None:
            return None

    monkeypatch.setattr(tg.session, "TelegramClient", FakeClient)
    config = Config(123, "hash", tmp_path / "main", "main")

    async def consume() -> None:
        async with client_for(config):
            pass

    asyncio.run(consume())

    assert "flood_sleep_threshold" not in captured
