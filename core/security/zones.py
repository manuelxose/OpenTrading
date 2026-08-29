"""Process-level trust-zone enforcement (architecture §29, INV-1, INV-9, ADR-0025).

Zone map:

- Zone 1 — internet / LLM providers / market data (advisory-only content).
- Zone 2 — Core Quant Platform (compartmentalized processes, least privilege).
- Zone 3 — broker / MT4 (execution capability lives here, behind a human gate).

LLM processes are Zone-1 consumers: they propose, never execute. This module is
the code-level gate that makes a live-mode LLM process fail closed at startup,
*before* any store, socket or secret is touched.
"""

from __future__ import annotations

from typing import Final

from core.domain.enums import OperatingMode

__all__ = [
    "EXECUTION_ZONE_MODES",
    "LLM_PROCESS_ALLOWED_MODES",
    "ExecutionBoundaryViolation",
    "assert_llm_process_cannot_execute",
]


class ExecutionBoundaryViolation(RuntimeError):
    """An LLM-facing process attempted to cross into the execution zone (INV-1)."""


#: Modes that grant execution capability over the broker boundary. Only the
#: dedicated live runtime and the operator API path may hold these.
EXECUTION_ZONE_MODES: Final[frozenset[OperatingMode]] = frozenset(
    {OperatingMode.LIVE_GATED, OperatingMode.LIVE_AUTO}
)

#: Modes an LLM-facing process is allowed to run in.
LLM_PROCESS_ALLOWED_MODES: Final[frozenset[OperatingMode]] = frozenset(
    {OperatingMode.RESEARCH, OperatingMode.BACKTEST, OperatingMode.PAPER}
)


def assert_llm_process_cannot_execute(mode: OperatingMode, *, process: str = "llm-process") -> None:
    """Fail closed if an LLM-facing process is started in an execution mode.

    Must be called at process startup, before any dependency (stores, sockets,
    secrets) is wired, so a misconfigured deployment can never put an LLM
    process on the execution path.
    """
    if mode in EXECUTION_ZONE_MODES:
        raise ExecutionBoundaryViolation(
            f"{process} is an LLM-facing process and cannot run in "
            f"operating mode {mode.value}: intelligence never has authority "
            f"over capital (INV-1, INV-9). Allowed modes: "
            f"{sorted(m.value for m in LLM_PROCESS_ALLOWED_MODES)}"
        )
