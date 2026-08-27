from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


def read_source(script: str) -> tuple[str, str]:
    if script == "-":
        return "<stdin>", sys.stdin.read()
    path = Path(script).expanduser().resolve()
    return str(path), path.read_text()


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


def runtime_namespace(
    client: Any, account: str, functions: ModuleType, types: ModuleType
) -> dict[str, Any]:
    return {
        "__name__": "__main__",
        "__file__": "<tg-run>",
        "client": client,
        "functions": functions,
        "types": types,
        "account": account,
    }
