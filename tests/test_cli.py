import asyncio
import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tg import cli
from tg.config import Config


def test_main_defaults_to_stdin(monkeypatch) -> None:
    received: dict[str, object] = {}

    async def run_script(account: str | None, script: str, script_args: list[str]) -> None:
        received.update(account=account, script=script, script_args=script_args)

    monkeypatch.setattr(cli, "run_script", run_script)

    assert cli.main([]) == 0
    assert received == {"account": None, "script": "-", "script_args": []}


def test_main_prints_help_for_bare_tty(monkeypatch, capsys) -> None:
    class TTY:
        def isatty(self) -> bool:
            return True

        def read(self) -> str:
            raise AssertionError("bare TTY must not read stdin")

    monkeypatch.setattr(cli.sys, "stdin", TTY())

    assert cli.main([]) == 2
    assert capsys.readouterr().out.startswith("usage: tg")


def test_empty_stdin_is_rejected_before_config(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO(" \n"))
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda *_args, **_kwargs: pytest.fail("empty stdin must not load config"),
    )

    assert cli.main([]) == 2
    assert capsys.readouterr().err == "tg: script is empty\n"


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


def test_missing_script_is_reported_as_tg_error(monkeypatch, capsys, tmp_path: Path) -> None:
    missing = tmp_path / "missing.py"
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda *_args, **_kwargs: pytest.fail("missing script must not load config"),
    )

    assert cli.main([str(missing)]) == 2
    assert (
        capsys.readouterr().err
        == f"tg: cannot read script {missing}: [Errno 2] No such file or directory: '{missing}'\n"
    )


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


def test_skill_command_prints_skill(capsys) -> None:
    assert cli.main(["skill"]) == 0
    assert "name: tg" in capsys.readouterr().out


def test_doctor_reports_authenticated_account_and_config_warning(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    config = Config(123, "hash", tmp_path / "main")
    config_path = tmp_path / "config.toml"
    config_path.touch(mode=0o644)
    config_path.chmod(0o644)
    monkeypatch.setenv("TG_CONFIG", str(config_path))
    session_file = tmp_path / "main.session"
    session_file.touch()

    class FakeClient:
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

    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        "config=ok",
        "account=ok name=main",
        f"session=ok path={session_file}",
        "telegram=connected",
        "auth=ok",
        "user=ok id=7 username=@example",
    ]
    assert captured.err == (
        f"warning=config is accessible by group/other users (mode 0644); "
        f"run `chmod 600 {config_path}`\n"
    )
