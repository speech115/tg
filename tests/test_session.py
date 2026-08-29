import asyncio
import stat
from pathlib import Path

import pytest

from tg import TgError
from tg.config import Config
from tg.session import client_for, session_lock


def test_session_lock_raises_typed_error(tmp_path: Path, monkeypatch) -> None:
    import tg.session

    def fail_lock(_fd: int, _operation: int) -> None:
        raise BlockingIOError

    monkeypatch.setattr(tg.session.fcntl, "flock", fail_lock)

    with pytest.raises(TgError, match="session is busy"):
        with session_lock(tmp_path / "main"):
            pass


def test_client_for_secures_session_directory_and_file(tmp_path: Path, monkeypatch) -> None:
    import tg.session

    session_root = tmp_path / "state"
    session_root.mkdir(mode=0o755)
    session_root.chmod(0o755)
    config = Config(123, "hash", session_root / "main")
    session_file = session_root / "main.session"

    class FakeClient:
        async def connect(self) -> None:
            session_file.touch()
            session_file.chmod(0o644)

        async def is_user_authorized(self) -> bool:
            return True

        async def disconnect(self) -> None:
            return None

    monkeypatch.setattr(tg.session, "TelegramClient", lambda *_args, **_kwargs: FakeClient())

    async def consume() -> None:
        async with client_for(config):
            pass

    asyncio.run(consume())

    assert stat.S_IMODE(session_root.stat().st_mode) == 0o700
    assert stat.S_IMODE(session_file.stat().st_mode) == 0o600
