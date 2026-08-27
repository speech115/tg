from pathlib import Path

import pytest

from tg.config import DEFAULT_SESSION_ROOT, load_config
from tg.errors import ConfigError


def test_load_config_maps_default_and_named_accounts_to_session_names(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
        [telegram]
        api_id = 123
        api_hash = "hash"
        """
    )

    default = load_config(config_path)
    selected = load_config(config_path, account="work")

    assert default.api_id == 123
    assert default.api_hash == "hash"
    assert default.session == DEFAULT_SESSION_ROOT / "main"
    assert default.account == "main"
    assert selected.session == DEFAULT_SESSION_ROOT / "work"
    assert selected.account == "work"


def test_obsolete_account_registry_fails(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        'default_account = "main"\n[accounts.main]\nsession = "~/main"\n'
        '[telegram]\napi_id = 123\napi_hash = "hash"\n'
    )

    with pytest.raises(ConfigError, match="account names map directly to session files"):
        load_config(config_path)


def test_legacy_inline_account_config_fails(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text('[telegram]\napi_id = 123\napi_hash = "hash"\nsession = "~/session"\n')

    with pytest.raises(ConfigError, match="account names map directly to session files"):
        load_config(config_path)


@pytest.mark.parametrize("name", ["", "../foo", "../../something", "/tmp/x", "bad name", "é"])
def test_account_name_must_match_safe_filename(name: str, tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text('[telegram]\napi_id = 123\napi_hash = "hash"\n')

    with pytest.raises(ConfigError, match="account must match"):
        load_config(config_path, account=name)


def test_account_name_accepts_hyphen_and_underscore(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text('[telegram]\napi_id = 123\napi_hash = "hash"\n')

    config = load_config(config_path, account="second-2_test")

    assert config.account == "second-2_test"
    assert config.session == DEFAULT_SESSION_ROOT / "second-2_test"


def test_missing_credentials_fail(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="TG_API_ID"):
        load_config(tmp_path / "missing.toml")


def test_tg_config_overrides_default_path(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "custom.toml"
    config_path.write_text('[telegram]\napi_id = 456\napi_hash = "custom"\n')
    monkeypatch.setenv("TG_CONFIG", str(config_path))

    config = load_config()

    assert config.api_id == 456
    assert config.api_hash == "custom"
