from pathlib import Path

import pytest

from tg.config import load_config
from tg.errors import ConfigError


def test_load_config_selects_default_and_named_accounts(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
        default_account = "main"

        [accounts.main]
        session = "~/main"

        [accounts.work]
        session = "~/work"

        [telegram]
        api_id = 123
        api_hash = "hash"
        """
    )

    default = load_config(config_path)
    selected = load_config(config_path, account="work")

    assert default.api_id == 123
    assert default.api_hash == "hash"
    assert default.session == Path("~/main").expanduser()
    assert default.account == "main"
    assert selected.session == Path("~/work").expanduser()
    assert selected.account == "work"


def test_unknown_account_fails(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        'default_account = "main"\n[accounts.main]\nsession = "~/main"\n'
        '[telegram]\napi_id = 123\napi_hash = "hash"\n'
    )

    with pytest.raises(ConfigError, match="unknown account 'work'"):
        load_config(config_path, account="work")


def test_legacy_inline_account_config_fails(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text('[telegram]\napi_id = 123\napi_hash = "hash"\nsession = "~/session"\n')

    with pytest.raises(ConfigError, match="accounts"):
        load_config(config_path)


def test_missing_credentials_fail(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="TG_API_ID"):
        load_config(tmp_path / "missing.toml")
