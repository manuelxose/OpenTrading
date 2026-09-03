from decimal import Decimal

import pytest
from core.config.settings import Settings
from core.domain.enums import OperatingMode
from engines.execution.live_runtime import build_live_execution_runtime
from engines.live_auto.config import LiveAutoViolation


def test_production_composition_is_authoritatively_live_gated() -> None:
    runtime = build_live_execution_runtime(
        Settings(
            operating_mode=OperatingMode.LIVE_GATED,
            live_approval_signing_key="x" * 32,
            live_operator_token="opentrading-test-operator-token-0123456789abcdef",
            live_max_quantity=Decimal("0.01"),
        )
    )
    assert runtime.gate is not None
    assert runtime.client is not None
    assert runtime.service is not None


def test_live_auto_composition_wires_the_deterministic_registry() -> None:
    runtime = build_live_execution_runtime(
        Settings(
            operating_mode=OperatingMode.LIVE_AUTO,
            live_auto_enabled=True,
            live_auto_max_strategies=1,
            live_auto_max_capital=Decimal("10000"),
            live_auto_max_loss=Decimal("1000"),
            live_max_quantity=Decimal("0.01"),
        )
    )
    assert runtime.live_auto is not None
    assert runtime.gate is None  # no human approval gate in automated mode
    assert runtime.client is not None
    assert runtime.service is not None


def test_live_auto_composition_fails_closed_when_disabled_by_default() -> None:
    with pytest.raises(LiveAutoViolation, match="disabled"):
        build_live_execution_runtime(
            Settings(
                operating_mode=OperatingMode.LIVE_AUTO,
                live_auto_enabled=False,
                live_auto_max_strategies=0,
                live_auto_max_capital=None,
                live_auto_max_loss=None,
            )
        )


def test_live_auto_composition_fails_closed_without_explicit_limits() -> None:
    with pytest.raises(LiveAutoViolation):
        build_live_execution_runtime(
            Settings(
                operating_mode=OperatingMode.LIVE_AUTO,
                live_auto_enabled=True,
                live_auto_max_strategies=2,
                live_auto_max_capital=None,
                live_auto_max_loss=None,
            )
        )
