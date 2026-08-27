from __future__ import annotations

import ast
import datetime as dt
import fcntl
import hashlib
import json
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .config import DEFAULT_USAGE_LOG, validate_account_name
from .errors import UsageError

REPEAT_THRESHOLD = 3
CANDIDATE_THRESHOLD = 5
_API_ROOTS = {"client", "functions", "types"}
_PRESERVED_NAMES = _API_ROOTS | {"account", "__file__", "__name__"}


def source_kind(script: str) -> str:
    return "stdin" if script == "-" else "file"


def _constant_kind(value: object) -> str:
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, complex):
        return "complex"
    if isinstance(value, bytes):
        return "bytes"
    if isinstance(value, str):
        return "str"
    return type(value).__name__


class _ShapeNormalizer(ast.NodeTransformer):
    def __init__(self) -> None:
        self._names: dict[str, str] = {}

    def visit_Constant(self, node: ast.Constant) -> ast.Constant:
        return ast.copy_location(
            ast.Constant(value=f"<{_constant_kind(node.value)}>"),
            node,
        )

    def visit_Name(self, node: ast.Name) -> ast.Name:
        if node.id in _PRESERVED_NAMES:
            return node
        name = self._names.setdefault(node.id, f"_v{len(self._names) + 1}")
        return ast.copy_location(ast.Name(id=name, ctx=node.ctx), node)

    def visit_arg(self, node: ast.arg) -> ast.arg:
        if node.arg not in _PRESERVED_NAMES:
            node.arg = self._names.setdefault(node.arg, f"_v{len(self._names) + 1}")
        return self.generic_visit(node)


def _api_path(node: ast.expr) -> str | None:
    parts: list[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name) and current.id in _API_ROOTS:
        return ".".join([current.id, *reversed(parts)])
    return None


def _argument_label(path: str, index: int) -> str:
    if path.endswith(".get_messages") or path.endswith(".iter_messages"):
        return "peer" if index == 0 else "arg"
    if path.endswith(".get_entity") or path.endswith(".download_media"):
        return "peer" if path.endswith(".get_entity") else "message"
    if path.endswith(".send_message"):
        return "peer" if index == 0 else "message"
    return "arg"


class _CallShape(ast.NodeVisitor):
    def __init__(self) -> None:
        self.calls: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        path = _api_path(node.func)
        if path and path != "client":
            args = [_argument_label(path, index) for index, _ in enumerate(node.args)]
            args.extend(keyword.arg or "kwargs" for keyword in node.keywords)
            rendered = f"{path}({', '.join(args)})"
            self.calls.append(rendered)
        self.generic_visit(node)


def analyze_source(source: str) -> tuple[str, str]:
    """Return a readable API shape and a value-redacted script fingerprint."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, TypeError):
        return "invalid Python", hashlib.sha256(b"invalid Python").hexdigest()

    calls = _CallShape()
    calls.visit(tree)
    shape = " → ".join(calls.calls[:12]) or "python script"
    if len(calls.calls) > 12:
        shape += " → …"

    normalized = _ShapeNormalizer().visit(tree)
    ast.fix_missing_locations(normalized)
    canonical = ast.dump(normalized, annotate_fields=True, include_attributes=False)
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return shape, fingerprint


def make_record(source: str, account: str, script: str, *, ok: bool) -> dict[str, Any]:
    shape, fingerprint = analyze_source(source)
    return {
        "ts": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "account": account,
        "source": source_kind(script),
        "shape": shape,
        "fingerprint": fingerprint,
        "ok": ok,
    }


def append_record(record: dict[str, Any], path: Path | None = None) -> None:
    if path is None:
        path = DEFAULT_USAGE_LOG
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    line = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
        os.fchmod(handle.fileno(), 0o600)
        # ponytail: one global usage-log lock; split logs only if throughput matters.
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.write(line)
            handle.flush()
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def read_records(path: Path | None = None) -> list[dict[str, Any]]:
    if path is None:
        path = DEFAULT_USAGE_LOG
    path = path.expanduser()
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        raise UsageError(f"cannot read usage log {path}: {exc}") from exc

    records: list[dict[str, Any]] = []
    for line in lines:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict):
            continue
        if not all(isinstance(value.get(key), str) for key in ("account", "shape", "fingerprint")):
            continue
        if not isinstance(value.get("ok"), bool):
            continue
        records.append(value)
    return records


def repeated(records: Iterable[dict[str, Any]], account: str | None = None) -> list[dict[str, Any]]:
    if account is not None:
        validate_account_name(account)
    grouped: dict[str, dict[str, Any]] = {}
    for record in records:
        if account is not None and record["account"] != account:
            continue
        fingerprint = record["fingerprint"]
        group = grouped.setdefault(
            fingerprint,
            {"shape": record["shape"], "fingerprint": fingerprint, "count": 0},
        )
        group["count"] += 1
    return sorted(grouped.values(), key=lambda item: (-item["count"], item["shape"]))


def format_report(records: Iterable[dict[str, Any]], account: str | None = None) -> str:
    groups = repeated(records, account)
    repeated_groups = [group for group in groups if group["count"] >= REPEAT_THRESHOLD]
    if not repeated_groups:
        return "No repeated operations."

    lines = ["Repeated shapes"]
    lines.extend(f"{group['count']}×  {group['shape']}" for group in repeated_groups)
    candidates = [group for group in repeated_groups if group["count"] >= CANDIDATE_THRESHOLD]
    if candidates:
        lines.extend(["", "Possible wrapper candidates (5+ runs)"])
        lines.extend(f"- {group['shape']}" for group in candidates)
    return "\n".join(lines)
