"""Error hierarchy for the Signal Fusion Engine (INV-16)."""

from __future__ import annotations

__all__ = [
    "CalibrationError",
    "CalibrationInsufficientDataError",
    "FusionConfigurationError",
    "FusionError",
]


class FusionError(Exception):
    """Base error for anything raised by the Signal Fusion Engine."""


class FusionConfigurationError(FusionError):
    """The fusion configuration is invalid or cannot cover the given inputs."""


class CalibrationError(FusionError):
    """Calibration failed for a data-related reason."""


class CalibrationInsufficientDataError(CalibrationError):
    """There is not enough labeled history to calibrate."""
