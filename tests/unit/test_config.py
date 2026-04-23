import pytest
from src.utils.config import Config


def test_config_loads_from_env(monkeypatch):
    monkeypatch.setenv("FACTURAMA_USER", "testuser")
    monkeypatch.setenv("FACTURAMA_PASSWORD", "testpass")
    config = Config.from_env()
    assert config.facturama_user == "testuser"
    assert config.facturama_password == "testpass"


def test_config_validate_raises_on_missing_credentials(monkeypatch):
    monkeypatch.delenv("FACTURAMA_USER", raising=False)
    monkeypatch.delenv("FACTURAMA_PASSWORD", raising=False)
    config = Config.from_env()
    with pytest.raises(ValueError, match="FACTURAMA_USER and FACTURAMA_PASSWORD"):
        config.validate()
