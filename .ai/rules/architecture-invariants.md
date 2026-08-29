# Architecture Invariants

These invariants are derived from `docs/architecture.md` and are **not negotiable**.
Any change to them requires an ADR (`docs/ADR/`) and Principal Architect review.
Violating an invariant is a blocking defect in any review, including Verification.

## INV-1 — Intelligence is never authority over capital

LLMs research, argue and propose. Deterministic code decides whether a trade may execute.
`TradingAgents` sizing/stop values are advisory only. No LLM path may ever transmit an order,
change risk limits, or change the operating mode. (Architecture §1, §3, §35)

## INV-2 — OrderIntent is the canonical crossing object

`Signal → Risk → OrderIntent → BACKTEST/PAPER (Nautilus) | LIVE (MT4 adapter)`.
Never `MT4Order`. Never three divergent implementations
(`backtest_strategy.py` / `paper_strategy.py` / `live_strategy.py`). (§5)

## INV-3 — Point-in-Time correctness

Every simulated-context query must accept `as_of`. During a backtest at time T nothing
posterior to T may be visible: prices, results, news, revisions, memory, embeddings,
postmortems, knowledge graph. No preloading the memory with the whole dataset.
Leakage tests must fail the build on violation. (§12)

## INV-4 — Risk Engine is deterministic

100% own code. No LLM, no agent, no prompt, no probabilistic interpretation.
`APPROVE` must carry `approved_quantity`, `approved_stop`, `policy_version`;
`REJECT` must carry `reason_codes`; `RESIZE` carries both the Risk-Engine-
computed approved values and the `reason_codes` that bounded the size
(ADR-0018). Property-based tests enforce "risk > limit → never approve". (§7)

## INV-5 — MT4 is execution-only

`QuantBridgeEA.mq4` is minimal: receive → validate → broker validation → send → report.
Strategy intelligence never migrates into MQL4. Defense-in-depth validations inside the EA
(symbol whitelist, lot limits, spread, quote freshness, duplicate `order_intent_id`,
command expiry). (§8)

## INV-6 — Reconciliation is mandatory

Never assume `send_order() == executed_trade`. State machine:
CANDIDATE → RISK_REJECTED → APPROVED → ORDER_INTENT → SUBMITTED → ACKNOWLEDGED →
PARTIALLY_FILLED → FILLED → CANCELLED → REJECTED → RECONCILED → CLOSED → REVIEWED.
Every restart reconciles DB state against broker state; divergence → SAFE_MODE. (§9)

## INV-7 — Kill switches and dead-man switch exist at every level

Strategy / instrument / portfolio (`NO_NEW_POSITIONS`) / emergency
(`CANCEL_PENDING`, `NO_NEW_POSITIONS`, optionally flatten). Heartbeat loss → broker-side
SL/TP remain, new trades BLOCKED. (§10)

## INV-8 — Only five operating modes

`RESEARCH`, `BACKTEST`, `PAPER`, `LIVE_GATED`, `LIVE_AUTO`.
A strategy reaches LIVE only through the promotion lifecycle
(IDEA → CANDIDATE → BACKTESTED → WALK_FORWARD_OK → ROBUSTNESS_OK → PAPER → SHADOW →
LIVE_GATED → LIVE_AUTO). No LLM may change the mode. (§6, §18)

## INV-9 — Trust zones

Zone 1: internet / LLM / market data. Zone 2: Core Quant Platform. Zone 3: broker / MT4.
LLMs never hold broker credentials, MT4 credentials, execution sockets, or secret-store access.
ZeroMQ transport is private only (WireGuard to Windows MT4), never internet-exposed. (§29)

## INV-10 — Data stores are separated by purpose

- PostgreSQL + TimescaleDB: transactional source of truth.
- Parquet + MinIO: heavy historical data (`/raw`, `/bronze`, `/silver`, `/gold`).
- Redis: cache, locks, ephemeral state, Redis Streams event bus.
- FalkorDB + Graphiti: temporal semantic memory.

Do not store one kind of data in another's store. (§13)

## INV-11 — Graphify ≠ Graphiti

Graphify = codebase knowledge for development context. Graphiti = temporal trading memory.
They must never be mixed. (§24)

## INV-12 — Frozen decisions require ADRs

The 20 frozen decisions (Python backend, TypeScript Command Center, MQL4 only in bridge,
TradingAgents as LLM committee, Qlib as quant platform, RD-Agent as R&D factory, Nautilus as
event-driven engine, Graphiti as temporal memory, FinMem inspiration-only, Obsidian as human
knowledge UI, Postgres truth, Parquet/MinIO history, Redis Streams bus, Langfuse AI
observability, Prometheus/Grafana ops observability, MT4 execution venue, ZeroMQ transport,
LLMs never control sizing/capital, research never auto-promotes to real money) may only be
revisited via ADR. (§34)

## INV-13 — Two runtimes, never merged

Core runtime Python 3.12 (TradingAgents, Graphiti, Nautilus, FastAPI, Risk, workers,
execution gateway). Quant R&D Python 3.11 on Linux (RD-Agent, Qlib, MLflow). (§4)

## INV-14 — Dependencies are pinned

`external-lock.yaml` records project, repository, tag, commit SHA, license, last reviewed.
Production never follows `main` / `latest` / `HEAD`. (§28)

## INV-15 — Domain events use the standard envelope

Every event on the bus carries `schema_version`, `event_id`, `trace_id`, `event_time`,
`ingested_at`, `producer`, `payload`, `provenance`. (§14)

## INV-16 — Signal Fusion weights are calibrated, not arbitrary

Fusion weights derive from historical validation; always compare Quant-only / LLM-only /
Quant+LLM / simple baseline; if the LLM adds no post-cost alpha, reduce or remove its weight.
(§16)
