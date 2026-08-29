"""Adapters to external systems.

Integration status:

- ``tradingagents`` — Phase 2, INTEGRATED read-only (MarketSnapshot →
  ResearchRequest → LLMSignal; ADR-0004). Strict boundary: only
  ``adapters/tradingagents/client.py`` imports upstream, lazily.
- ``market_data``   — Phase 1, INTEGRATED (normalization, point-in-time snapshots)
- ``graphiti``      — Phase 3 (temporal memory, as_of retrieval; ADR-0008)
- ``nautilus``      — Phase 4 (deterministic backtesting/paper venue; ADR-0007)
- ``qlib``          — Phase 9 (quant research platform; ADR-0005)
- ``rdagent``       — Phase 9 (offline R&D factory; ADR-0006)
- ``mt4``           — Phase 6 (execution-only bridge; ADR-0003, INV-5)

The domain layer in ``core/`` never imports any of these (enforced by test).
"""
