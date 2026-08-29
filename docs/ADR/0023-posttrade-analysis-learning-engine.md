# ADR-0023: Post-trade analysis & learning engine — deterministic postmortems with four sinks

- Status: accepted
- Date: 2026-08-27
- Deciders: principal-architect (+ posttrade + risk + execution + verification)

## Context

Architecture §17 (*Post-trade learning loop*) requires that a closed trade
trigger a second process: execution analysis, performance attribution, thesis
and signal evaluation, risk evaluation, postmortem, Graphiti episode and
strategy statistics — computing PnL, R multiple, alpha, slippage, fees, MAE,
MFE, time in trade, entry/exit efficiency, signal calibration, prediction
error and regime, and learning from the gap between expected and actual.

The Phase 7 pipeline (ADR-0022) emitted a placeholder `PostTradeReview` with no
real analysis, no persisted metrics and no reconciliation gate. INV-1 requires
that no learning path may change risk limits; INV-10 separates the four stores
by purpose; INV-6 requires that a trade be definitively closed *and
reconciled* before downstream state is final.

## Decision

**Implement the post-trade learning engine as a deterministic analysis stage
that writes four sinks and never touches risk limits.**

1. **Reconciliation gate (`apps/worker/stages/posttrade.py`)** — the stage
   consumes `trade.closed` but completes only when every order referenced by
   the outcome is terminal (`CLOSED` / `RECONCILED` / `REVIEWED`) in the
   execution store. A pending trade raises
   `PostTradeReconciliationPendingError`: the message stays unacked and is
   redelivered until reconciliation catches up — the stage never silently
   marks a pending postmortem SUCCEEDED.

2. **Deterministic analysis (`engines/posttrade/`)** — pure functions, no IO,
   no clocks, no LLM:
   - `metrics.py` — canonical per-trade metrics: gross/net PnL, fees,
     slippage, R multiple (net PnL over the approved risk amount), alpha
     (actual − expected, or actual − benchmark when supplied), MAE/MFE from
     the observed price path (never fabricated: an empty path yields `None`),
     holding time, TradingView-style entry/exit efficiency, per-producer Brier
     calibration error, prediction error, market regime.
   - `analysis.py` — independent quality evaluations of QuantSignal,
     LLMSignal, FusedSignal (each judged against the realized move, with
     calibration and disagreement notes), RiskDecision (limits respected,
     approved size respected, planned stop honored — read-only) and execution
     (slippage/fees vs notional); expected-vs-actual comparison, deterministic
     lessons and a SUPPORTED/CONTRADICTED/INCONCLUSIVE verdict.
   - The price path is recorded by the paper ledger
     (`record_mark`/`price_path`, bounded rolling window) from every snapshot
     observed while the position is open; heavy history stays in MinIO.

3. **Trade context capture (`trade_contexts`, migration 0005)** — while the
   trade is live, the research/fusion/proposal/risk stages persist their
   canonical outputs per entry trace, so a postmortem after a worker restart
   reconstructs the full decision chain without replaying the event stream.

4. **Four sinks** (each independently switchable; failures of the non-canonical
   sinks audit and never block the postmortem):
   - **PostgreSQL** (`posttrade_reviews`, migration 0005) — canonical typed
     columns for every metric plus the full review payload (JSONB); idempotent
     by `review_id` = UUIDv5(trade_id).
   - **MinIO** (`posttrade-artifacts` bucket) — immutable audit artifact:
     review + metrics + trade context + price path, deterministic key
     `reviews/<year>/<month>/<review_id>.json`.
   - **Graphiti** — LONG_TERM `MemoryEpisode` ("postmortem" lesson) with
     Instrument/Strategy/Trade entities, expected-vs-actual and lessons in
     the episode content.
   - **Obsidian** — the stage renders a rich markdown note under
     `50_Postmortems/<year>/<instrument>/` and sets `vault_path` on the
     review; the existing `ObsidianExporter` mirror preserves that canonical
     note instead of duplicating it.

5. **Risk-limit immutability (INV-1)** — `engines/posttrade` has no import of
   the risk engine or `RiskPolicy`; the analyzer only reads the
   `RiskDecision` produced at entry. A static invariant test fails the build
   if any post-trade module imports risk writers, and a behavioral test
   proves analysis leaves the decision byte-identical.

6. **Terminal bookkeeping** — every order of the trade (entry and closing
   intents, both carried on the outcome) reaches REVIEWED; entry and closing
   lifecycles reach REVIEWED; the observed price path is released.

## Consequences

- Every closed-and-reconciled trade produces a traceable postmortem and a
  memory episode (Definition of Done), reconstructable from PostgreSQL alone.
- Post-trade analysis can never move risk limits automatically; policy changes
  require the promotion/adjudication paths (ADR-0015/0018).
- Metrics follow documented definitions; future live-mode work reuses the same
  pure engine with venue-reported slippage/fees and reconciled order states.
