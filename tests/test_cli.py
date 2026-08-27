import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tg import cli
from tg.config import Config
from tg.errors import SessionBusyError


def test_run_parser_preserves_script_arguments() -> None:
    args = cli.build_parser().parse_args(["--account", "work", "run", "script.py", "--limit", "2"])

    assert args.account == "work"
    assert args.command == "run"
    assert args.script == "script.py"
    assert args.script_args == ["--limit", "2"]


def test_usage_parser_is_available() -> None:
    args = cli.build_parser().parse_args(["usage"])

    assert args.command == "usage"


def test_main_formats_session_busy(monkeypatch, capsys) -> None:
    async def fail(*_args: object, **_kwargs: object) -> None:
        raise SessionBusyError("session is busy: /tmp/main")

    monkeypatch.setattr(cli, "run_script", fail)

    assert cli.main(["run", "-"]) == 2
    assert capsys.readouterr().err == "tg: session is busy: /tmp/main\n"


def test_main_passes_account_and_script_args(monkeypatch) -> None:
    received: dict[str, object] = {}

    async def run_script(
        config_path: Path, account: str | None, script: str, script_args: list[str]
    ) -> None:
        received.update(
            config_path=config_path,
            account=account,
            script=script,
            script_args=script_args,
        )

    monkeypatch.setattr(cli, "run_script", run_script)

    assert cli.main(["--account", "work", "run", "script.py", "one", "--flag"]) == 0
    assert received == {
        "config_path": cli.DEFAULT_CONFIG,
        "account": "work",
        "script": "script.py",
        "script_args": ["one", "--flag"],
    }


def test_run_script_records_completed_shape_without_script_values(
    monkeypatch, tmp_path: Path
) -> None:
    config = Config(123, "hash", tmp_path / "main", "main")
    usage_path = tmp_path / "usage.jsonl"

    class FakeClient:
        pass

    class ClientContext:
        async def __aenter__(self):
            return FakeClient()

        async def __aexit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(cli, "load_config", lambda *_args, **_kwargs: config)
    monkeypatch.setattr(
        cli,
        "read_source",
        lambda _script: (
            "<stdin>",
            'await client.get_messages("private-chat", limit=20)\n',
        ),
    )
    monkeypatch.setattr(cli, "client_for", lambda *_args, **_kwargs: ClientContext())
    monkeypatch.setattr(cli, "execute", lambda *_args, **_kwargs: asyncio.sleep(0))
    monkeypatch.setattr(cli.usage_log, "DEFAULT_USAGE_LOG", usage_path)

    asyncio.run(cli.run_script(Path("config.toml"), None, "-", []))

    record = json.loads(usage_path.read_text())
    assert record["account"] == "main"
    assert record["source"] == "stdin"
    assert record["shape"] == "client.get_messages(peer, limit)"
    assert record["ok"] is True
    assert "private-chat" not in usage_path.read_text()


def test_run_script_records_failed_execution(monkeypatch, tmp_path: Path) -> None:
    config = Config(123, "hash", tmp_path / "main", "main")
    usage_path = tmp_path / "usage.jsonl"

    class ClientContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_args: object) -> None:
            return None

    async def fail(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("script failed")

    monkeypatch.setattr(cli, "load_config", lambda *_args, **_kwargs: config)
    monkeypatch.setattr(cli, "read_source", lambda _script: ("<stdin>", "print('x')"))
    monkeypatch.setattr(cli, "client_for", lambda *_args, **_kwargs: ClientContext())
    monkeypatch.setattr(cli, "execute", fail)
    monkeypatch.setattr(cli.usage_log, "DEFAULT_USAGE_LOG", usage_path)

    with pytest.raises(RuntimeError, match="script failed"):
        asyncio.run(cli.run_script(Path("config.toml"), None, "-", []))

    record = json.loads(usage_path.read_text())
    assert record["ok"] is False


def test_run_script_records_client_cleanup_failure(monkeypatch, tmp_path: Path) -> None:
    config = Config(123, "hash", tmp_path / "main", "main")
    usage_path = tmp_path / "usage.jsonl"

    class ClientContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_args: object) -> None:
            raise RuntimeError("disconnect failed")

    monkeypatch.setattr(cli, "load_config", lambda *_args, **_kwargs: config)
    monkeypatch.setattr(cli, "read_source", lambda _script: ("<stdin>", "print('x')"))
    monkeypatch.setattr(cli, "client_for", lambda *_args, **_kwargs: ClientContext())
    monkeypatch.setattr(cli, "execute", lambda *_args, **_kwargs: asyncio.sleep(0))
    monkeypatch.setattr(cli.usage_log, "DEFAULT_USAGE_LOG", usage_path)

    with pytest.raises(RuntimeError, match="disconnect failed"):
        asyncio.run(cli.run_script(Path("config.toml"), None, "-", []))

    record = json.loads(usage_path.read_text())
    assert record["ok"] is False


def test_empty_account_is_rejected_in_cli(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text('[telegram]\napi_id = 123\napi_hash = "hash"\n')

    assert cli.main(["--config", str(config_path), "--account", "", "doctor"]) == 2
    assert capsys.readouterr().err == "tg: account must match [A-Za-z0-9_-]+\n"


def test_module_entrypoint_preserves_failure_exit_code(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "tg", "--config", str(tmp_path / "missing.toml"), "doctor"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert result.stderr.startswith("tg: set TG_API_ID")


def test_doctor_reports_authenticated_account(monkeypatch, capsys, tmp_path: Path) -> None:
    config = Config(123, "hash", tmp_path / "main", "main")
    session_file = tmp_path / "main.session"
    session_file.touch()

    class FakeClient:
        async def is_user_authorized(self) -> bool:
            return True

        async def get_me(self):
            return type("User", (), {"id": 7, "username": "example"})()

    class ClientContext:
        async def __aenter__(self):
            return FakeClient()

        async def __aexit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(cli, "load_config", lambda *_args, **_kwargs: config)
    monkeypatch.setattr(cli, "client_for", lambda *_args, **_kwargs: ClientContext())

    asyncio.run(cli.doctor(tmp_path / "config.toml", None))

    assert capsys.readouterr().out.splitlines() == [
        "config=ok",
        "account=ok name=main",
        f"session=ok path={session_file}",
        "telegram=connected",
        "auth=ok",
        "user=ok id=7 username=@example",
    ]
