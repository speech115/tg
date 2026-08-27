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


def load_config(path: Path = DEFAULT_CONFIG) -> Config:
    path = path.expanduser()
    data: dict[str, object] = {}
    if path.exists():
        try:
            with path.open("rb") as handle:
                parsed = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ConfigError(f"cannot read config {path}: {exc}") from exc
        section = parsed.get("telegram", {})
        if not isinstance(section, dict):
            raise ConfigError("[telegram] must be a table")
        data = section

    api_id_raw = os.environ.get("TG_API_ID", data.get("api_id"))
    api_hash = os.environ.get("TG_API_HASH", data.get("api_hash"))
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

    session_raw = os.environ.get("TG_SESSION", data.get("session", str(DEFAULT_SESSION)))
    account = os.environ.get("TG_ACCOUNT", data.get("account", "main"))
    if not isinstance(session_raw, str) or not session_raw:
        raise ConfigError("telegram.session must be a non-empty string")
    if not isinstance(account, str) or not account:
        raise ConfigError("telegram.account must be a non-empty string")
    return Config(api_id, api_hash, Path(session_raw).expanduser(), account)
