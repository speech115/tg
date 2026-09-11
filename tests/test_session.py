import asyncio
import fcntl
import multiprocessing
import os
import selectors
import signal
import stat
import subprocess
import sys
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

    async def consume() -> None:
        with pytest.raises(TgError, match="session is busy"):
            async with session_lock(tmp_path / "main", timeout=0):
                pytest.fail("busy session must not be entered")

    asyncio.run(consume())


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


def _hold_lock(session: Path, control) -> None:
    # A separate process using the same OS lock, without any Telegram connection.
    with session.with_name(f"{session.name}.lock").open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.truncate(0)
        handle.write(f"{os.getpid()}\n")
        handle.flush()
        control.send(True)
        control.recv()


@pytest.fixture
def lock_owner(tmp_path: Path):
    context = multiprocessing.get_context("spawn")
    control, child = context.Pipe()
    session = tmp_path / "main"
    process = context.Process(target=_hold_lock, args=(session, child))
    process.start()
    child.close()
    try:
        assert control.poll(5) and control.recv(), "lock owner failed to start"
        yield session, process, control
    finally:
        if process.is_alive():
            try:
                control.send(None)
            except OSError:
                pass
        control.close()
        process.join(3)
        if process.is_alive():
            process.kill()
            process.join(3)
        process.close()


def test_waits_for_other_process_without_blocking_event_loop(lock_owner, capsys) -> None:
    session, owner, release = lock_owner
    entered = []

    async def run() -> None:
        async def waiter() -> None:
            async with session_lock(session, timeout=2):
                entered.append(True)
                with pytest.raises(TgError, match="session is busy"):
                    async with session_lock(session, timeout=0):
                        pytest.fail("two owners acquired the same session")

        task = asyncio.create_task(waiter())
        try:
            await asyncio.sleep(0.05)
            assert not entered
            async with session_lock(session.with_name("media"), timeout=0):
                assert not entered  # another named session remains usable
            release.send(None)
            await asyncio.wait_for(task, 3)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(run())
    assert entered == [True]
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.count("waiting") == 1
    assert f"pid={owner.pid}" in captured.err


@pytest.mark.parametrize("timeout", [0, 0.05])
def test_timeout_preserves_owner_metadata_and_does_not_connect(lock_owner, monkeypatch, timeout):
    import tg.session

    session, owner, _ = lock_owner
    lock = session.with_name("main.lock")
    original = lock.read_bytes()
    monkeypatch.setattr(
        tg.session, "TelegramClient", lambda *_a, **_kw: pytest.fail("connected while busy")
    )

    async def run() -> None:
        with pytest.raises(TgError, match=f"session is busy: .*pid={owner.pid}.*timeout"):
            async with client_for(Config(123, "hash", session), lock_timeout=timeout):
                pytest.fail("busy client entered")

    asyncio.run(run())
    assert lock.read_bytes() == original


def test_cancelled_waiter_does_not_release_another_process_lock(lock_owner) -> None:
    session, _, _ = lock_owner

    async def run() -> None:
        async def wait() -> None:
            async with session_lock(session, timeout=2):
                pytest.fail("waiter unexpectedly acquired lock")

        task = asyncio.create_task(wait())
        await asyncio.sleep(0.02)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(TgError, match="session is busy"):
            async with session_lock(session, timeout=0):
                pytest.fail("cancellation unlocked another process")

    asyncio.run(run())


def test_killed_owner_releases_lock_without_deleting_file(lock_owner) -> None:
    session, owner, _ = lock_owner
    lock = session.with_name("main.lock")
    inode = lock.stat().st_ino
    owner.kill()
    owner.join(3)
    assert not owner.is_alive()

    async def run() -> None:
        async with session_lock(session, timeout=0):
            assert lock.stat().st_ino == inode
            assert lock.read_text().strip() == str(os.getpid())

    asyncio.run(run())
    assert lock.exists()


def test_default_client_waits_before_constructing_and_holds_lock_until_disconnect(
    lock_owner, monkeypatch
) -> None:
    import tg.session

    session, _, release = lock_owner
    calls = []

    class FakeClient:
        def __init__(self, *_args, **_kwargs):
            calls.append("created")

        async def connect(self):
            calls.append("connected")

        async def is_user_authorized(self):
            return True

        async def disconnect(self):
            with pytest.raises(TgError, match="session is busy"):
                async with session_lock(session, timeout=0):
                    pytest.fail("lock released before disconnect")
            calls.append("disconnected")

    monkeypatch.setattr(tg.session, "TelegramClient", FakeClient)

    async def run() -> None:
        async def consume() -> None:
            async with client_for(Config(123, "hash", session)):
                calls.append("entered")
                raise RuntimeError("script failure")

        task = asyncio.create_task(consume())
        try:
            await asyncio.sleep(0.05)
            assert not calls
            release.send(None)
            with pytest.raises(RuntimeError, match="script failure"):
                await asyncio.wait_for(task, 3)
            async with session_lock(session, timeout=0):
                pass
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(run())
    assert calls == ["created", "connected", "entered", "disconnected"]


@pytest.mark.parametrize("timeout", [-1, float("nan"), float("inf")])
def test_invalid_lock_timeout_is_rejected(tmp_path, timeout) -> None:
    async def run() -> None:
        with pytest.raises(TgError, match="finite non-negative"):
            async with session_lock(tmp_path / "main", timeout=timeout):
                pytest.fail("invalid timeout accepted")

    asyncio.run(run())


def test_cli_sigint_cancels_wait_without_touching_owner(lock_owner, tmp_path: Path) -> None:
    session, owner, _ = lock_owner
    script = tmp_path / "read.py"
    script.write_text("pass\n")
    code = (
        "import sys\nfrom pathlib import Path\nfrom tg import cli\nfrom tg.config import Config\n"
        "cli.load_config = lambda **kw: Config(123, 'hash', Path(sys.argv[1]))\n"
        "raise SystemExit(cli.main(['--lock-timeout', '5', sys.argv[2]]))\n"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", code, str(session), str(script)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stderr, selectors.EVENT_READ)
            assert selector.select(5), "wait diagnostic was not emitted"
            assert "waiting" in process.stderr.readline()
        process.send_signal(signal.SIGINT)
        out, err = process.communicate(timeout=3)
        assert process.returncode == 130
        assert out == ""
        assert "tg: interrupted" in err
        assert owner.is_alive()
        assert session.with_name("main.lock").read_text().strip() == str(owner.pid)
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=3)
