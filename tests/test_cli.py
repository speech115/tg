import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tg import cli
from tg.config import Config
from tg.errors import SessionBusyError


def test_script_parser_preserves_script_arguments() -> None:
    args = cli.build_parser().parse_args(["--account", "work", "script.py", "--limit", "2"])

    assert args.account == "work"
    assert args.target == "script.py"
    assert args.target_args == ["--limit", "2"]


def test_bare_parser_defaults_to_stdin() -> None:
    args = cli.build_parser().parse_args([])

    assert args.target is None
    assert args.target_args == []


@pytest.mark.parametrize("command", ["login", "doctor", "usage", "skill"])
def test_reserved_commands_are_parsed_as_targets(command: str) -> None:
    args = cli.build_parser().parse_args([command])

    assert args.target == command
    assert args.target_args == []


def test_main_defaults_to_stdin(monkeypatch) -> None:
    received: dict[str, object] = {}

    async def run_script(account: str | None, script: str, script_args: list[str]) -> None:
        received.update(account=account, script=script, script_args=script_args)

    monkeypatch.setattr(cli, "run_script", run_script)

    assert cli.main([]) == 0
    assert received == {"account": None, "script": "-", "script_args": []}


def test_main_formats_session_busy(monkeypatch, capsys) -> None:
    async def fail(*_args: object, **_kwargs: object) -> None:
        raise SessionBusyError("session is busy: /tmp/main")

    monkeypatch.setattr(cli, "run_script", fail)

    assert cli.main(["-"]) == 2
    assert capsys.readouterr().err == "tg: session is busy: /tmp/main\n"


def test_main_passes_account_and_script_args(monkeypatch) -> None:
    received: dict[str, object] = {}

    async def run_script(account: str | None, script: str, script_args: list[str]) -> None:
        received.update(account=account, script=script, script_args=script_args)

    monkeypatch.setattr(cli, "run_script", run_script)

    assert cli.main(["--account", "work", "script.py", "one", "--flag"]) == 0
    assert received == {
        "account": "work",
        "script": "script.py",
        "script_args": ["one", "--flag"],
    }


def test_removed_run_command_is_rejected(capsys) -> None:
    assert cli.main(["run", "-"]) == 2
    assert "tg run" in capsys.readouterr().err


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

    asyncio.run(cli.run_script(None, "-", []))

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
        asyncio.run(cli.run_script(None, "-", []))

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
        asyncio.run(cli.run_script(None, "-", []))

    record = json.loads(usage_path.read_text())
    assert record["ok"] is False


def test_empty_account_is_rejected_in_cli(monkeypatch, tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text('[telegram]\napi_id = 123\napi_hash = "hash"\n')
    monkeypatch.setenv("TG_CONFIG", str(config_path))

    assert cli.main(["--account", "", "doctor"]) == 2
    assert capsys.readouterr().err == "tg: account must match [A-Za-z0-9_-]+\n"


def test_module_entrypoint_uses_tg_config(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "missing.toml"
    environment = os.environ | {"TG_CONFIG": str(config_path)}

    result = subprocess.run(
        [sys.executable, "-m", "tg", "doctor"],
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode == 2
    assert result.stderr.startswith("tg: set TG_API_ID")


def test_skill_command_prints_skill(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "read_skill", lambda: "# bundled skill\n")

    assert cli.main(["skill"]) == 0
    assert capsys.readouterr().out == "# bundled skill\n"


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

    asyncio.run(cli.doctor(None))

    assert capsys.readouterr().out.splitlines() == [
        "config=ok",
        "account=ok name=main",
        f"session=ok path={session_file}",
        "telegram=connected",
        "auth=ok",
        "user=ok id=7 username=@example",
    ]
