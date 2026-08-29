from __future__ import annotations

import fcntl
from collections.abc import Iterator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

from telethon import TelegramClient

from . import TgError
from .config import Config


def _secure_session(config: Config) -> None:
    root = config.session.parent
    session = (
        config.session
        if config.session.suffix == ".session"
        else config.session.with_name(f"{config.session.name}.session")
    )
    try:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root.chmod(0o700)
        if session.exists():
            session.chmod(0o600)
    except OSError as exc:
        raise TgError(f"cannot secure Telegram session {root}: {exc}") from exc


@contextmanager
def session_lock(session: Path) -> Iterator[None]:
    lock_path = session.with_name(f"{session.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise TgError(f"session is busy: {session}") from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@asynccontextmanager
async def client_for(config: Config, *, require_auth: bool = True):
    _secure_session(config)
    with session_lock(config.session):
        client = TelegramClient(
            str(config.session),
            config.api_id,
            config.api_hash,
        )
        try:
            await client.connect()
            _secure_session(config)
            if require_auth and not await client.is_user_authorized():
                raise TgError("Telegram session is not authorized; run `tg login`")
            yield client
        finally:
            await client.disconnect()
