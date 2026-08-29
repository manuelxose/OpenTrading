"""MT4 execution settings (OT_MT4_* environment variables).

Mirrors the pattern of :mod:`core.config.settings` — pydantic-settings with the
``OT_`` prefix; secrets never committed (INV-9). These settings configure the
Core-side client; the emulator accepts plain endpoints plus these defaults.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from adapters.mt4.protocol import PROTOCOL_VERSION

__all__ = ["Mt4Settings", "get_mt4_settings"]


class Mt4Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OT_MT4_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    command_addr: str = "tcp://127.0.0.1:5555"
    events_addr: str = "tcp://127.0.0.1:5556"
    quotes_addr: str = "tcp://127.0.0.1:5557"
    protocol_version: str = PROTOCOL_VERSION
    heartbeat_interval_seconds: float = 1.0
    degraded_after_seconds: float = 3.0
    down_after_seconds: float = 6.0
    request_timeout_seconds: float = 5.0


def get_mt4_settings() -> Mt4Settings:
    """Process-wide MT4 settings singleton (matching core get_settings)."""
    return Mt4Settings()
