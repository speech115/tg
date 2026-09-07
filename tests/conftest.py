import pytest


@pytest.fixture(autouse=True)
def isolate_config_env(monkeypatch) -> None:
    for name in ("TG_API_ID", "TG_API_HASH", "TG_CONFIG"):
        monkeypatch.delenv(name, raising=False)
