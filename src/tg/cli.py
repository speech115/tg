from __future__ import annotations

import argparse
import asyncio
import sys

from telethon import types
from telethon.tl import functions

from . import usage as usage_log
from .config import load_config
from .errors import NotAuthenticatedError, TgError
from .run import execute, read_source, runtime_namespace
from .session import client_for
from .skill import read_skill

_COMMANDS = frozenset({"login", "doctor", "usage", "skill"})
_REMOVED_COMMANDS = frozenset({"run"})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tg",
        description="Authenticated Telegram Python harness.",
        epilog=(
            "Commands: login, doctor, usage, skill.\n"
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
    config = load_config(account=account)
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


async def doctor(account: str | None) -> None:
    config = load_config(account=account)
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


def skill() -> None:
    content = read_skill()
    print(content, end="" if content.endswith("\n") else "\n")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    target = args.target
    try:
        if target in _REMOVED_COMMANDS:
            raise TgError("`tg run` was removed; pass a script directly or pipe Python to `tg`")
        if target in _COMMANDS:
            if args.target_args:
                raise TgError(f"tg {target} does not accept arguments")
            if target == "login":
                asyncio.run(login(args.account))
            elif target == "doctor":
                asyncio.run(doctor(args.account))
            elif target == "usage":
                usage(args.account)
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
