"""Broker reconciliation and Safe Mode (INV-6, architecture §9).

Execution state is persisted in PostgreSQL, every restart reconciles against
live broker state, and unexplained material divergence flips the platform into
SAFE_MODE (new positions blocked; monitoring, reconciliation and risk-reducing
actions still allowed).
"""

from __future__ import annotations

from engines.execution.applier import ExecutionDivergenceError, OrderStateApplier
from engines.execution.emergency import (
    EMERGENCY_STRATEGY_ID,
    EmergencyController,
    EmergencyControlViolation,
    EmergencyPolicy,
)
from engines.execution.emergency_persistence import (
    EmergencyStore,
    InMemoryEmergencyStore,
    PostgresEmergencyStore,
)
from engines.execution.persistence import (
    ExecutionStateStore,
    InMemoryExecutionStateStore,
    PostgresExecutionStateStore,
)
from engines.execution.reconciler import BrokerReconciler, BrokerView, VenueViewPosition
from engines.execution.safe_mode import SafeModeController, SafeModeViolation
from engines.execution.service import ExecutionService

__all__ = [
    "EMERGENCY_STRATEGY_ID",
    "BrokerReconciler",
    "BrokerView",
    "EmergencyControlViolation",
    "EmergencyController",
    "EmergencyPolicy",
    "EmergencyStore",
    "ExecutionDivergenceError",
    "ExecutionService",
    "ExecutionStateStore",
    "InMemoryEmergencyStore",
    "InMemoryExecutionStateStore",
    "OrderStateApplier",
    "PostgresEmergencyStore",
    "PostgresExecutionStateStore",
    "SafeModeController",
    "SafeModeViolation",
    "VenueViewPosition",
]
