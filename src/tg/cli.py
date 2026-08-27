from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from telethon import types
from telethon.tl import functions

from . import usage as usage_log
from .config import DEFAULT_CONFIG, load_config
from .errors import NotAuthenticatedError, TgError
from .run import execute, read_source, runtime_namespace
from .session import client_for


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tg")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--account", metavar="NAME")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("login")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("script", help="Python file or - for stdin")
    run_parser.add_argument("script_args", nargs=argparse.REMAINDER)
    subparsers.add_parser("doctor")
    subparsers.add_parser("usage")
    return parser


async def login(config_path: Path, account: str | None) -> None:
    config = load_config(config_path, account=account)
    async with client_for(config, require_auth=False) as client:
        await client.start()
    print(f"logged in: {config.account}", file=sys.stderr)


async def run_script(
    config_path: Path, account: str | None, script: str, script_args: list[str]
) -> None:
    config = load_config(config_path, account=account)
    filename, source = read_source(script)
    started = False
    ok = False
    try:
        async with client_for(config) as client:
            started = True
            await execute(
                source,
                filename,
                runtime_namespace(client, config.account, functions, types),
                argv=[filename if script != "-" else "-", *script_args],
            )
        ok = True
    finally:
        if started:
            try:
                usage_log.append_record(
                    usage_log.make_record(source, config.account, script, ok=ok)
                )
            except OSError:
                pass


async def doctor(config_path: Path, account: str | None) -> None:
    config = load_config(config_path, account=account)
    session_file = config.session
    if session_file.suffix != ".session":
        session_file = session_file.with_name(f"{session_file.name}.session")
    session_status = "ok" if session_file.exists() else "missing"
    print("config=ok")
    print(f"account=ok name={config.account}")
    print(f"session={session_status} path={session_file}")
    if session_status == "missing":
        raise NotAuthenticatedError(f"session is missing: {session_file}; run `tg login`")
    async with client_for(config, require_auth=False) as client:
        if not await client.is_user_authorized():
            raise NotAuthenticatedError("account is not authorized; run `tg login`")
        me = await client.get_me()
    username = f"@{me.username}" if me.username else "-"
    print("telegram=connected")
    print("auth=ok")
    print(f"user=ok id={me.id} username={username}")


def usage(account: str | None) -> None:
    print(usage_log.format_report(usage_log.read_records(), account))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "login":
            asyncio.run(login(args.config, args.account))
        elif args.command == "doctor":
            asyncio.run(doctor(args.config, args.account))
        elif args.command == "usage":
            usage(args.account)
        else:
            asyncio.run(run_script(args.config, args.account, args.script, args.script_args))
    except TgError as exc:
        print(f"tg: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("tg: interrupted", file=sys.stderr)
        return 130
    return 0
