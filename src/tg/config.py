from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .errors import ConfigError

DEFAULT_CONFIG = Path("~/.config/tg/config.toml").expanduser()
DEFAULT_SESSION = Path("~/.local/state/tg/main").expanduser()


@dataclass(frozen=True)
class Config:
    api_id: int
    api_hash: str
    session: Path = DEFAULT_SESSION
    account: str = "main"


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


def _credentials(data: dict[str, object], path: Path) -> tuple[int, str, dict[str, object]]:
    telegram = _table(data.get("telegram"), "[telegram]")
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
    return api_id, api_hash, telegram


def _account(
    data: dict[str, object], telegram: dict[str, object], requested: str | None
) -> tuple[str, Path]:
    if "session" in telegram or "account" in telegram:
        raise ConfigError("use default_account and [accounts.<name>].session")

    accounts_raw = data.get("accounts")
    if accounts_raw is None:
        if "default_account" in data:
            raise ConfigError("accounts must be a non-empty table")
        accounts: dict[str, object] = {"main": {"session": str(DEFAULT_SESSION)}}
    else:
        accounts = _table(accounts_raw, "accounts")
        if not accounts:
            raise ConfigError("accounts must be a non-empty table")

    default = data.get("default_account", "main")
    if not isinstance(default, str) or not default:
        raise ConfigError("default_account must be a non-empty string")
    name = requested or default
    if not name:
        raise ConfigError("account must be a non-empty string")
    entry = accounts.get(name)
    if entry is None:
        available = ", ".join(sorted(accounts))
        raise ConfigError(f"unknown account '{name}' (available: {available})")
    account = _table(entry, f"[accounts.{name}]")
    session_raw = account.get("session")
    if not isinstance(session_raw, str) or not session_raw:
        raise ConfigError(f"[accounts.{name}].session must be a non-empty string")
    return name, Path(session_raw).expanduser()


def load_config(path: Path = DEFAULT_CONFIG, *, account: str | None = None) -> Config:
    path = path.expanduser()
    data = _read_data(path)
    api_id, api_hash, telegram = _credentials(data, path)
    selected, session = _account(data, telegram, account)
    return Config(api_id, api_hash, session, selected)
