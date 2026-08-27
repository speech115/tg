from pathlib import Path

import pytest

from tg.config import load_config
from tg.errors import ConfigError


def test_load_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        '[telegram]\napi_id = 123\napi_hash = "hash"\nsession = "~/session"\naccount = "work"\n'
    )

    config = load_config(config_path)

    assert config.api_id == 123
    assert config.api_hash == "hash"
    assert config.session == Path("~/session").expanduser()
    assert config.account == "work"


def test_missing_credentials_fail(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="TG_API_ID"):
        load_config(tmp_path / "missing.toml")
