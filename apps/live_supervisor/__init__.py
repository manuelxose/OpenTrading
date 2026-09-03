"""Deterministic LIVE_AUTO trading supervisor (apps/live_supervisor).

The supervisor is the *only* process allowed to originate automated orders in
LIVE_AUTO mode. Every capital decision is deterministic (INV-1): baseline
momentum signals on broker quotes → mandatory Risk Engine → LIVE_AUTO registry
authorization → MT4 boundary. No LLM, no RD-Agent, no strategy process.
"""

from apps.live_supervisor.engine import LiveTradingEngine, OrderSubmitter

__all__ = ["LiveTradingEngine", "OrderSubmitter"]
