"""MT4 execution adapter — Phase 6, execution-only bridge (ADR-0003, INV-5).

Versioned ZeroMQ protocol between the Core and MetaTrader 4: wire messages,
idempotency/sequence/expiry gates, a deterministic simulated broker, the
Core-side client, and the Python MT4 emulator that lets lifecycle tests run
without MetaTrader itself (Phase 6 DoD, ADR-0020).
"""

from adapters.mt4.broker import BrokerConfig, SimulatedBroker, SymbolSpec
from adapters.mt4.client import Mt4ExecutionClient
from adapters.mt4.emulator import Mt4Emulator
from adapters.mt4.errors import Mt4ErrorCode, Mt4ProtocolError, ProtocolErrorDetail
from adapters.mt4.guards import CommandGate, GateOutcome
from adapters.mt4.ledger import IntentLedger, SequenceTracker
from adapters.mt4.protocol import PROTOCOL_VERSION
from adapters.mt4.transport import ConnectionHealth, Mt4Endpoints

__all__ = [
    "PROTOCOL_VERSION",
    "BrokerConfig",
    "CommandGate",
    "ConnectionHealth",
    "GateOutcome",
    "IntentLedger",
    "Mt4Emulator",
    "Mt4Endpoints",
    "Mt4ErrorCode",
    "Mt4ExecutionClient",
    "Mt4ProtocolError",
    "ProtocolErrorDetail",
    "SequenceTracker",
    "SimulatedBroker",
    "SymbolSpec",
]
