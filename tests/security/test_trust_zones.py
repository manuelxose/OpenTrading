"""Trust-zone invariants (INV-1, INV-9, ADR-0025).

These tests encode the Definition of Done of the security-hardening milestone:

    A compromised LLM worker cannot directly submit a broker order.

Chain: the worker refuses live operating modes → the worker source never
imports the MT4 execution client → the live client itself fails closed without
a human-approval authorizer. The approval-gate behaviour itself is covered in
``tests/execution/`` (gate state machine, signature verification, kill switches).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from adapters.mt4.client import Mt4ExecutionClient
from core.config.settings import Settings
from core.domain.enums import OperatingMode
from core.security import (
    LLM_PROCESS_ALLOWED_MODES,
    ExecutionBoundaryViolation,
    assert_llm_process_cannot_execute,
)

WORKER_PKG = Path(__file__).resolve().parents[2] / "apps" / "worker"


class TestLlmProcessZoneGuard:
    def test_live_modes_are_forbidden(self) -> None:
        for mode in (OperatingMode.LIVE_GATED, OperatingMode.LIVE_AUTO):
            with pytest.raises(ExecutionBoundaryViolation):
                assert_llm_process_cannot_execute(mode, process="worker-under-test")

    def test_research_paper_modes_are_allowed(self) -> None:
        for mode in LLM_PROCESS_ALLOWED_MODES:
            assert_llm_process_cannot_execute(mode, process="worker-under-test")

    def test_worker_cli_fails_closed_in_live_gated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from apps.worker import cli

        monkeypatch.setattr(
            cli,
            "get_settings",
            lambda: Settings(operating_mode=OperatingMode.LIVE_GATED),
        )
        with pytest.raises(ExecutionBoundaryViolation):
            cli.main(["run-once"])

    def test_worker_cli_refuses_live_auto(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from apps.worker import cli

        monkeypatch.setattr(
            cli,
            "get_settings",
            lambda: Settings(operating_mode=OperatingMode.LIVE_AUTO),
        )
        with pytest.raises(ExecutionBoundaryViolation):
            cli.main(["run"])


class TestWorkerHasNoExecutionCapability:
    def test_worker_source_never_imports_mt4_execution(self) -> None:
        """The worker package must not contain a single import of the MT4
        execution client: a compromised LLM process therefore has no code path
        to the broker."""
        for path in WORKER_PKG.rglob("*.py"):
            source = path.read_text()
            assert "adapters.mt4" not in source, (
                f"{path.relative_to(WORKER_PKG.parents[1])} imports the MT4 "
                f"execution client — LLM processes must never hold execution "
                f"capability (INV-1, INV-9)"
            )

    def test_worker_pipeline_has_no_mt4_capability(self) -> None:
        from apps.worker.pipeline import ALL_STAGES

        # Every stage lives in apps.worker and (per the source-scan test above)
        # never imports adapters.mt4; the only "execution" stage is the Nautilus
        # paper venue, which cannot reach a broker.
        for stage in ALL_STAGES:
            assert stage.__module__.startswith("apps.worker."), stage.__module__


class TestLiveClientFailsClosed:
    def test_live_gated_client_requires_authorizer(self) -> None:
        with pytest.raises(ValueError):
            Mt4ExecutionClient(operating_mode=OperatingMode.LIVE_GATED)
