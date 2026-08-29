import os
import re
import stat
import tomllib
from dataclasses import dataclass
from pathlib import Path

from . import TgError

DEFAULT_CONFIG = Path("~/.config/tg/config.toml").expanduser()
DEFAULT_ACCOUNT = "main"
DEFAULT_SESSION_ROOT = Path("~/.local/state/tg").expanduser()


@dataclass(frozen=True)
class Config:
    api_id: int
    api_hash: str
    session: Path


def validate_account_name(name: str) -> str:
    if not isinstance(name, str) or re.fullmatch(r"[A-Za-z0-9_-]+", name) is None:
        raise TgError("account must match [A-Za-z0-9_-]+")
    return name


def resolve_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return path.expanduser()
    override = os.environ.get("TG_CONFIG")
    return Path(override).expanduser() if override else DEFAULT_CONFIG


def config_permissions_warning(path: Path) -> str | None:
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        return None
    except OSError as exc:
        return f"cannot inspect config permissions: {exc}"
    if mode & 0o077:
        return (
            f"config is accessible by group/other users (mode {mode:04o}); run `chmod 600 {path}`"
        )
    return None


def load_config(path: Path | None = None, *, account: str | None = None) -> Config:
    path = resolve_config_path(path)
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError:
        data = {}
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise TgError(f"cannot read config {path}: {exc}") from exc

    telegram = data.get("telegram")
    if telegram is None:
        telegram = {}
    elif not isinstance(telegram, dict):
        raise TgError("[telegram] must be a table")

    api_id_raw = os.environ.get("TG_API_ID", telegram.get("api_id"))
    api_hash = os.environ.get("TG_API_HASH", telegram.get("api_hash"))
    if api_id_raw is None or api_hash is None:
        raise TgError(
            f"set TG_API_ID/TG_API_HASH or create {path} with [telegram].api_id and api_hash"
        )
    try:
        api_id = int(api_id_raw)
    except (TypeError, ValueError) as exc:
        raise TgError("telegram.api_id must be an integer") from exc
    if not isinstance(api_hash, str) or not api_hash:
        raise TgError("telegram.api_hash must be a non-empty string")

    name = validate_account_name(DEFAULT_ACCOUNT if account is None else account)
    return Config(api_id, api_hash, DEFAULT_SESSION_ROOT / name)
