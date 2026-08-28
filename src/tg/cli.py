from __future__ import annotations

import argparse
import ast
import asyncio
import inspect
import sys
from importlib.resources import files
from pathlib import Path
from typing import Any

from telethon import types
from telethon.tl import functions

from . import TgError
from .config import config_permissions_warning, load_config, resolve_config_path
from .session import client_for

_COMMANDS = frozenset({"login", "doctor", "skill"})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tg",
        description="Authenticated Telegram Python harness.",
        epilog=(
            "Commands: login, doctor, skill.\n"
            "Without a command, tg executes COMMAND|SCRIPT or reads Python from stdin."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--account", metavar="NAME")
    parser.add_argument("target", nargs="?", metavar="COMMAND|SCRIPT")
    parser.add_argument("target_args", nargs=argparse.REMAINDER, metavar="ARGS")
    return parser


async def login(account: str | None) -> None:
    config = load_config(account=account)
    async with client_for(config, require_auth=False) as client:
        await client.start()
    print(f"logged in: {config.account}", file=sys.stderr)


async def run_script(
    account: str | None,
    script: str,
    script_args: list[str],
) -> None:
    filename, source = read_source(script)
    if not source.strip():
        raise TgError("script is empty")
    config = load_config(account=account)
    async with client_for(config) as client:
        await execute(
            source,
            filename,
            {
                "__name__": "__main__",
                "client": client,
                "functions": functions,
                "types": types,
                "account": config.account,
            },
            argv=[filename if script != "-" else "-", *script_args],
        )


async def doctor(account: str | None) -> None:
    config_path = resolve_config_path()
    config = load_config(account=account)
    if warning := config_permissions_warning(config_path):
        print(f"warning={warning}", file=sys.stderr)
    session_file = config.session
    if session_file.suffix != ".session":
        session_file = session_file.with_name(f"{session_file.name}.session")
    session_status = "ok" if session_file.exists() else "missing"
    print("config=ok")
    print(f"account=ok name={config.account}")
    print(f"session={session_status} path={session_file}")
    if session_status == "missing":
        raise TgError(f"session is missing: {session_file}; run `tg login`")
    async with client_for(config, require_auth=False) as client:
        if not await client.is_user_authorized():
            raise TgError("account is not authorized; run `tg login`")
        me = await client.get_me()
    username = f"@{me.username}" if me.username else "-"
    print("telegram=connected")
    print("auth=ok")
    print(f"user=ok id={me.id} username={username}")


def skill() -> None:
    try:
        content = files("tg").joinpath("SKILL.md").read_text(encoding="utf-8")
    except FileNotFoundError:
        source_path = Path(__file__).resolve().parents[2] / "skills" / "tg" / "SKILL.md"
        try:
            content = source_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise TgError(f"cannot read bundled skill: {exc}") from exc
    print(content, end="" if content.endswith("\n") else "\n")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    target = args.target
    if target is None and sys.stdin.isatty():
        parser.print_help()
        return 2
    try:
        if target in _COMMANDS:
            if args.target_args:
                raise TgError(f"tg {target} does not accept arguments")
            if target == "login":
                asyncio.run(login(args.account))
            elif target == "doctor":
                asyncio.run(doctor(args.account))
            else:
                skill()
        else:
            asyncio.run(run_script(args.account, target or "-", args.target_args))
    except TgError as exc:
        print(f"tg: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("tg: interrupted", file=sys.stderr)
        return 130
    return 0


def read_source(script: str) -> tuple[str, str]:
    if script == "-":
        return "<stdin>", sys.stdin.read()
    path = Path(script).expanduser().resolve()
    try:
        return str(path), path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise TgError(f"cannot read script {path}: {exc}") from exc


async def execute(
    source: str,
    filename: str,
    namespace: dict[str, Any],
    *,
    argv: list[str] | None = None,
) -> None:
    previous_argv = sys.argv
    previous_path = sys.path[:]
    namespace["__file__"] = filename
    sys.argv = [filename] if argv is None else list(argv)
    if not filename.startswith("<"):
        sys.path.insert(0, str(Path(filename).expanduser().resolve().parent))
    try:
        code = compile(source, filename, "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
        result = eval(code, namespace)
        if inspect.isawaitable(result):
            await result
    finally:
        sys.argv = previous_argv
        sys.path[:] = previous_path
