from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from telethon import types
from telethon.tl import functions

from .config import DEFAULT_CONFIG, load_config
from .errors import TgError
from .run import execute, read_source, runtime_namespace
from .session import client_for


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tg")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("login")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("script", help="Python file or - for stdin")
    return parser


async def login(config_path: Path) -> None:
    config = load_config(config_path)
    async with client_for(config, require_auth=False) as client:
        await client.start()
    print(f"logged in: {config.account}", file=sys.stderr)


async def run_script(config_path: Path, script: str) -> None:
    config = load_config(config_path)
    filename, source = read_source(script)
    async with client_for(config) as client:
        await execute(
            source,
            filename,
            runtime_namespace(client, config.account, functions, types),
        )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "login":
            asyncio.run(login(args.config))
        else:
            asyncio.run(run_script(args.config, args.script))
    except TgError as exc:
        print(f"tg: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("tg: interrupted", file=sys.stderr)
        return 130
    return 0
