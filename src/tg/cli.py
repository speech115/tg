import argparse
import ast
import asyncio
import inspect
import math
import sys
from importlib.resources import files
from pathlib import Path
from types import CodeType, ModuleType
from typing import Any

from telethon import types
from telethon.tl import functions

from . import TgError
from .config import config_permissions_warning, load_config, resolve_config_path
from .session import DEFAULT_LOCK_TIMEOUT, client_for

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
    parser.add_argument(
        "--lock-timeout",
        type=float,
        default=DEFAULT_LOCK_TIMEOUT,
        metavar="SECONDS",
        help="wait for a busy session (default: 120 seconds; 0: fail immediately)",
    )
    parser.add_argument("target", nargs="?", metavar="COMMAND|SCRIPT")
    parser.add_argument("target_args", nargs=argparse.REMAINDER, metavar="ARGS")
    return parser


async def login(account: str | None, *, lock_timeout: float = DEFAULT_LOCK_TIMEOUT) -> None:
    config = load_config(account=account)
    async with client_for(config, require_auth=False, lock_timeout=lock_timeout) as client:
        await client.start()
    print(f"logged in: {config.session.name}", file=sys.stderr)


async def run_script(
    account: str | None,
    script: str,
    script_args: list[str],
    *,
    lock_timeout: float = DEFAULT_LOCK_TIMEOUT,
) -> None:
    filename, source = read_source(script)
    if not source.strip():
        raise TgError("script is empty")
    code = compile(source, filename, "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
    config = load_config(account=account)
    async with client_for(config, lock_timeout=lock_timeout) as client:
        await execute(
            code,
            {
                "client": client,
                "functions": functions,
                "types": types,
                "account": config.session.name,
            },
            argv=[filename if script != "-" else "-", *script_args],
        )


async def doctor(account: str | None, *, lock_timeout: float = DEFAULT_LOCK_TIMEOUT) -> None:
    config_path = resolve_config_path()
    config = load_config(account=account)
    if warning := config_permissions_warning(config_path):
        print(f"warning={warning}", file=sys.stderr)
    session_file = config.session.with_suffix(".session")
    session_status = "ok" if session_file.exists() else "missing"
    print("config=ok")
    print(f"account=ok name={config.session.name}")
    print(f"session={session_status} path={session_file}")
    if session_status == "missing":
        raise TgError(f"session is missing: {session_file}; run `tg login`")
    async with client_for(config, lock_timeout=lock_timeout) as client:
        me = await client.get_me()
    username = f"@{me.username}" if me.username else "-"
    print("telegram=connected")
    print("auth=ok")
    print(f"user=ok id={me.id} username={username}")


def skill() -> None:
    try:
        content = files("tg").joinpath("SKILL.md").read_text(encoding="utf-8")
    except OSError as exc:
        raise TgError(f"cannot read bundled skill: {exc}") from exc
    print(content, end="" if content.endswith("\n") else "\n")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not math.isfinite(args.lock_timeout) or args.lock_timeout < 0:
        parser.error("--lock-timeout must be a finite non-negative number")
    target = args.target
    if target is None and sys.stdin.isatty():
        parser.print_help()
        return 2
    try:
        if target in _COMMANDS:
            if args.target_args:
                raise TgError(f"tg {target} does not accept arguments")
            if target == "login":
                asyncio.run(login(args.account, lock_timeout=args.lock_timeout))
            elif target == "doctor":
                asyncio.run(doctor(args.account, lock_timeout=args.lock_timeout))
            else:
                skill()
        else:
            asyncio.run(
                run_script(
                    args.account, target or "-", args.target_args, lock_timeout=args.lock_timeout
                )
            )
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
    code: CodeType,
    namespace: dict[str, Any],
    *,
    argv: list[str] | None = None,
) -> None:
    filename = code.co_filename
    module = ModuleType("__main__")
    module.__dict__.update(namespace)
    module.__file__ = filename
    previous_argv = sys.argv
    previous_path = sys.path[:]
    previous_main = sys.modules["__main__"]
    try:
        sys.argv = [filename] if argv is None else list(argv)
        sys.path.insert(0, "" if filename.startswith("<") else str(Path(filename).parent))
        sys.modules["__main__"] = module
        result = eval(code, module.__dict__)
        if inspect.isawaitable(result):
            await result
    finally:
        sys.argv = previous_argv
        sys.path[:] = previous_path
        sys.modules["__main__"] = previous_main
