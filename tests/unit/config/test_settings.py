"""Settings tests: env-var overrides and enum validation."""

from __future__ import annotations

import pytest
from core.config.settings import Settings, get_settings
from core.domain.enums import OperatingMode
from pydantic import ValidationError


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OT_OPERATING_MODE", raising=False)
    settings = Settings()
    assert settings.operating_mode is OperatingMode.RESEARCH
    assert settings.app_name == "opentrading-core"
    assert settings.schema_version == "1.0.0"
    assert settings.audit_enabled is True


def test_env_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OT_OPERATING_MODE", "PAPER")
    settings = Settings()
    assert settings.operating_mode is OperatingMode.PAPER


def test_invalid_mode_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OT_OPERATING_MODE", "HYPERSPEED")
    with pytest.raises(ValidationError):
        Settings()


def test_weak_live_secrets_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(live_operator_token="short")
    with pytest.raises(ValidationError):
        Settings(live_operator_token="")
    with pytest.raises(ValidationError):
        Settings(live_approval_signing_key="x" * 16)
    Settings(live_operator_token="x" * 32, live_approval_signing_key="y" * 32)


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OT_OPERATING_MODE", "BACKTEST")
    assert get_settings() is get_settings()
    assert get_settings().operating_mode is OperatingMode.BACKTEST
