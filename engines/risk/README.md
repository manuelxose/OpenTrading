# engines/risk — Deterministic Risk & Policy Engine (Phase 5)

The most important component (architecture §7, INV-4, ADR-0015, ADR-0018).
100% own deterministic code; no LLM, no agent, no prompt-based decisions.

## Usage

```python
from engines.risk import evaluate_proposal

decision = evaluate_proposal(
    proposal=...,
    account=...,
    portfolio=...,
    snapshot=...,
    strategy=...,
    policy=...,
    instrument=...,
)
# decision.decision ∈ {APPROVE, RESIZE, REJECT}
```

## Decision model (ADR-0018)

- `APPROVE` — proposal quantity accepted unchanged (no reason codes).
- `RESIZE` — approved quantity reduced by the engine; carries the reason codes
  that bounded the size.
- `REJECT` — a hard violation; carries the reason codes; never approved values.

The approved quantity is **always** computed by the engine (INV-1); an LLM
"BUY 100 lots" can only become a REJECT or a reduced RESIZE.

## Checks

Hard checks (always REJECT): strategy active, symbol whitelist, quote
freshness, broker connected, heartbeat, safe mode, trading schedule, daily
loss, rolling drawdown, loss-sequence cooldown, max positions, max orders,
spread, slippage, stop distance.

Soft checks (resize the quantity): per-trade risk budget, instrument /
asset-class / currency / total exposure, leverage, margin, min/max size,
lot step.

## Determinism

The engine is a pure function of its inputs: no state, no IO, no wall clock.
`inputs_hash` (SHA-256 over canonical inputs) and the decision id are stable
across runs. See `tests/risk/` for unit, boundary, property-based and fuzz
tests enforcing "risk > limit → NEVER APPROVE".
