# Phase 7 — Post-trade analysis & learning engine (ADR-0023)

Implements architecture §17 (*Post-trade learning loop*): a closed trade starts
a second process — analysis, attribution, thesis/signal/risk/execution
evaluation, postmortem and memory.

```
trade.closed (TradeOutcome)
     │
     ▼
reconciliation gate ── pending ──► PostTradeReconciliationPendingError
     │                                  (unacked redelivery until CLOSED/RECONCILED)
     ▼
engines/posttrade.analyze
     ├─ metrics: PnL, fees, slippage, R, alpha, MAE, MFE, holding time,
     │           entry/exit efficiency, calibration, prediction error, regime
     ├─ signal quality: quant / llm / fused / memory (independent, vs realized)
     ├─ risk quality: limits respected, size respected, stop honored (read-only)
     ├─ execution quality: slippage/fees vs notional
     ├─ expected vs actual (the gap the memory learns from)
     └─ lessons + verdict (SUPPORTED / CONTRADICTED / INCONCLUSIVE)
     │
     ├─► PostgreSQL  posttrade_reviews (typed canonical metrics + payload)
     ├─► MinIO       posttrade-artifacts bucket (immutable audit artifact)
     ├─► Graphiti    LONG_TERM MemoryEpisode (semantic lesson)
     └─► Obsidian    50_Postmortems/<year>/<instrument>/<date>-<short>.md
     │
     ▼
order REVIEWED × trade orders · lifecycles REVIEWED · price path released
```

## Key design points

- **Reconciliation gate** — the stage consumes `trade.closed` but completes only
  when every order on the outcome is terminal (`CLOSED` / `RECONCILED` /
  `REVIEWED`). Pending trades *fail* the stage (never silently succeed), so the
  bus redelivers until reconciliation catches up (INV-6).
- **Deterministic engine** — `engines/posttrade` is pure Python with no IO,
  clocks, LLM or risk-limit writes (INV-1, INV-4). MAE/MFE derive from the
  observed price path recorded by the ledger while the position was open; an
  empty path yields `None` — the loop never fabricates excursion data.
- **Trade context capture** — `trade_contexts` (migration 0005) persists the
  entry trace's quant / llm / fused / proposal / risk_decision outputs while the
  trade is live, so a postmortem after a worker restart reconstructs the full
  decision chain without replaying the event stream.
- **Four sinks, one DoD** — canonical metrics always land in PostgreSQL (the
  DoD backbone; failures retry via redelivery). MinIO / Graphiti / Obsidian
  outages are audited and never block the postmortem. `review_id` is a
  deterministic UUIDv5 over the trade id, so replays are idempotent.
- **Risk limits are immutable** — the engine never imports the risk engine or
  `RiskPolicy`; it only reads the entry `RiskDecision`. A static test fails the
  build if any post-trade module imports risk writers (INV-1).

## Files

| Path | Responsibility |
|---|---|
| `core/schemas/posttrade.py` | `TradeMetrics`, `SignalQualityRecord`, `RiskQualityRecord`, `ExecutionQualityRecord`, `PostTradeReviewRecord`, `TradeContextRecord` |
| `engines/posttrade/metrics.py` | pure metric computation |
| `engines/posttrade/analysis.py` | independent quality evaluations + verdict |
| `engines/posttrade/persistence.py` | `posttrade_reviews` store (InMemory + Postgres) |
| `engines/posttrade/artifacts.py` | MinIO artifact store + audit payload |
| `engines/posttrade/notes.py` | Obsidian note rendering |
| `apps/worker/stages/posttrade.py` | reconciliation gate + orchestration |
| `migrations/versions/0005_posttrade_learning.py` | `posttrade_reviews` + `trade_contexts` |

## Tests

- `tests/unit/posttrade/` — metric math, independent analysis, persistence
  round-trip, artifacts, notes, risk-limit immutability.
- `tests/worker/test_posttrade_learning.py` — end-to-end DoD: closed trade →
  postmortem + memory episode, redelivery idempotency, reconciliation gate.
- `tests/integration/test_posttrade_integration.py` (OT_INTEGRATION gated) —
  PostgreSQL store + migration against the docker stack.
