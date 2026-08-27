from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .errors import ConfigError

DEFAULT_CONFIG = Path("~/.config/tg/config.toml").expanduser()
DEFAULT_ACCOUNT = "main"
DEFAULT_SESSION_ROOT = Path("~/.local/state/tg").expanduser()


@dataclass(frozen=True)
class Config:
    api_id: int
    api_hash: str
    session: Path = DEFAULT_SESSION_ROOT / DEFAULT_ACCOUNT
    account: str = DEFAULT_ACCOUNT


def _read_data(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"cannot read config {path}: {exc}") from exc
    return data


def _table(value: object, name: str) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"{name} must be a table")
    return value


def _credentials(telegram: dict[str, object], path: Path) -> tuple[int, str]:
    api_id_raw = os.environ.get("TG_API_ID", telegram.get("api_id"))
    api_hash = os.environ.get("TG_API_HASH", telegram.get("api_hash"))
    if api_id_raw is None or api_hash is None:
        raise ConfigError(
            f"set TG_API_ID/TG_API_HASH or create {path} with [telegram].api_id and api_hash"
        )
    try:
        api_id = int(api_id_raw)
    except (TypeError, ValueError) as exc:
        raise ConfigError("telegram.api_id must be an integer") from exc
    if not isinstance(api_hash, str) or not api_hash:
        raise ConfigError("telegram.api_hash must be a non-empty string")
    return api_id, api_hash


def _session(account: str | None) -> tuple[str, Path]:
    name = account or DEFAULT_ACCOUNT
    if not name or name in {".", ".."} or Path(name).name != name:
        raise ConfigError("account must be a simple name")
    return name, DEFAULT_SESSION_ROOT / name


def load_config(path: Path = DEFAULT_CONFIG, *, account: str | None = None) -> Config:
    path = path.expanduser()
    data = _read_data(path)
    telegram = _table(data.get("telegram"), "[telegram]")
    if any(key in data for key in ("default_account", "accounts")) or any(
        key in telegram for key in ("session", "account")
    ):
        raise ConfigError(
            "account names map directly to session files; remove account/session registry entries"
        )
    api_id, api_hash = _credentials(telegram, path)
    selected, session = _session(account)
    return Config(api_id, api_hash, session, selected)
