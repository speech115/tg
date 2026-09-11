import asyncio
import fcntl
import math
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from telethon import TelegramClient

from . import TgError
from .config import Config

DEFAULT_LOCK_TIMEOUT = 120.0


def _secure_session(config: Config) -> None:
    root = config.session.parent
    session = config.session.with_suffix(".session")
    try:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root.chmod(0o700)
        if session.exists():
            session.chmod(0o600)
    except OSError as exc:
        raise TgError(f"cannot secure Telegram session {root}: {exc}") from exc


@asynccontextmanager
async def session_lock(
    session: Path, *, timeout: float = DEFAULT_LOCK_TIMEOUT
) -> AsyncIterator[None]:
    if not math.isfinite(timeout) or timeout < 0:
        raise TgError("lock timeout must be a finite non-negative number")
    lock_path = session.with_name(f"{session.name}.lock")
    with lock_path.open("a+") as handle:
        owner = "unknown"
        announced = False
        try:
            async with asyncio.timeout(timeout):
                while True:
                    try:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        handle.seek(0)
                        owner = handle.read(32).strip()
                        if not owner.isdecimal():
                            owner = "unknown"
                        if not announced and timeout:
                            print(
                                f"tg: session is busy: {session} (holder pid={owner}); "
                                f"waiting up to {timeout:g}s",
                                file=sys.stderr,
                                flush=True,
                            )
                            announced = True
                        # ponytail: polling is not FIFO; add a broker only if ordering matters.
                        await asyncio.sleep(0.1)
        except TimeoutError as exc:
            raise TgError(
                f"session is busy: {session} (holder pid={owner}); lock timeout after {timeout:g}s"
            ) from exc
        handle.seek(0)
        handle.truncate()
        handle.write(f"{os.getpid()}\n")
        handle.flush()
        yield


@asynccontextmanager
async def client_for(
    config: Config, *, require_auth: bool = True, lock_timeout: float = DEFAULT_LOCK_TIMEOUT
):
    _secure_session(config)
    async with session_lock(config.session, timeout=lock_timeout):
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
