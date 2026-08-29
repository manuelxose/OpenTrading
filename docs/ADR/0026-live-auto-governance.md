# ADR-0026 — LIVE_AUTO governance: automated live trading, disabled by default

- Status: accepted
- Date: 2026-08-29
- Deciders: principal-architect + security (execution-sensitive routing)
- Supersedes: none. Implements architecture §6 (LIVE_AUTO) and Phase 11.

## Context

Architecture Phase 11 defines `LIVE_AUTO`: promoted strategies may trade without
per-trade human approval, but only under deterministic governance, and only after an
explicit administrative transition from `LIVE_GATED`. The capability did not exist in
code beyond the canonical enums (`OperatingMode.LIVE_AUTO`, `StrategyState.LIVE_AUTO`).
This ADR turns Phase 11's Definition of Done into enforceable code:

> Cambiar una estrategia a LIVE_AUTO requiere una acción administrativa explícita y
> queda registrada. Un LLM no puede realizarla.

## Decision

1. **Disabled by default.** `OT_LIVE_AUTO_ENABLED=false` (Settings default). Enabling
   requires `live_auto_max_strategies`, `live_auto_max_capital` and `live_auto_max_loss`
   to be explicitly positive — `LiveAutoConfig.assert_enabled()` fails closed otherwise.
   `build_live_execution_runtime` refuses to wire `LIVE_AUTO` while disabled.
2. **Registry as the authority.** New `engines/live_auto/` package:
   `LiveAutoRegistry` + durable `live_auto_strategies` / `live_auto_pnl_ledger` tables
   (migration 0008). The registry is deterministic code only — it imports nothing from
   any LLM, strategy or research module, like the emergency control system.
3. **Administrative promotion only.** `LIVE_GATED → LIVE_AUTO` happens exclusively via
   the operator-authenticated API (`POST /api/v1/live-auto/promotions`), requires
   `from_state=LIVE_GATED`, enforces the strategy/capital/risk-budget ceilings, and
   writes an immutable `audit_events` row (`live_auto.strategy_promoted`).
   `PromotionDecision` rejects `to_state=LIVE_AUTO` outright — strategy code and
   RD-Agent can never self-promote.
4. **Operating mode is immutable at runtime.** It comes from `OT_OPERATING_MODE` at
   process start; there is no endpoint to change it. LLM processes refuse to start in
   `LIVE_AUTO` (`core/security/zones.py`); the RD-Agent bootstrap rejects
   `OT_OPERATING_MODE=LIVE_AUTO` (`services/quant_rd`).
5. **Risk Engine mandatory.** `ExecutionService.submit` for a `LIVE_AUTO` intent
   requires a `RiskDecision`; the registry verifies APPROVE/RESIZE, the exact
   `risk_decision_id`, `approved_quantity == intent.quantity`, and
   `risk_amount ≤ per-strategy risk budget`.
6. **All other controls stay mandatory.** Emergency/kill switches and the dead-man
   switch gate every submission (`EmergencyController.assert_can_enter`), MT4 local
   safety controls stay wired (quantity ceiling, quote freshness, mutation authorizer),
   and the MT4 client fail-closes without an authorizer in `LIVE_AUTO`.
7. **Global loss limit.** An append-only realized-PnL ledger (operator-authenticated
   `POST /api/v1/live-auto/pnl`, or deterministic posttrade integration) feeds the
   authorizer; cumulative realized loss at the limit blocks all new automated entries.
   Ledger rows are never updated or deleted.
8. **Full auditability.** Every automated order records `live_auto.order_authorized`
   or `live_auto.order_denied` through `PostgresAuditSink` into the immutable
   `audit_events` table; the execution path already persists every OrderRecord and
   reconciliation event (INV-6).

## Consequences

- Operators must explicitly enable and budget LIVE_AUTO; defaults are safe.
- The automated path adds one deterministic check per submission (registry read);
  the check runs against PostgreSQL like the human approval gate reads its store.
- The per-strategy risk budget is set at promotion time; an optional settings map
  (`live_auto_strategy_risk_budgets`) caps promotion budgets per strategy.
- PnL ledger feeding is operator-driven until the posttrade engine is wired as a
  deterministic ledger writer (follow-up).
