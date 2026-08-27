import asyncio
from pathlib import Path

from tg import cli
from tg.config import Config
from tg.errors import SessionBusyError


def test_run_parser_preserves_script_arguments() -> None:
    args = cli.build_parser().parse_args(["--account", "work", "run", "script.py", "--limit", "2"])

    assert args.account == "work"
    assert args.command == "run"
    assert args.script == "script.py"
    assert args.script_args == ["--limit", "2"]


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
