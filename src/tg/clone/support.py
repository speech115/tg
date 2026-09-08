"""Clone errors, safe terminal output and durable local file replacement."""

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from tg import TgError


class PolicyError(TgError):
    def __init__(self, message: str, **details):
        super().__init__(message)
        self.details = details


class RateLimitError(PolicyError):
    def __init__(self, seconds: int):
        super().__init__(f"Telegram cooldown: retry in {seconds}s", retry_after=seconds)


def sanitize(value) -> str:
    return "".join(c if c >= " " and not "\x7f" <= c <= "\x9f" else " " for c in str(value))


def note(value) -> None:
    print(sanitize(value), file=sys.stderr)


def json_default(value):
    if isinstance(value, bytes):
        return {"bytes": value.hex()}
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "to_dict"):
        return value.to_dict()
    raise TypeError(f"cannot encode {type(value).__name__}")


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=json_default)


def replace_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
