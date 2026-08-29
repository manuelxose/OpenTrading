# ADR-0022: Autonomous PAPER pipeline — Redis Streams stages, idempotent run ledger, recovery semantics

- Status: accepted
- Date: 2026-08-27
- Deciders: principal-architect (+ worker-pipeline + risk + execution + verification)

## Context

Phase 7 (architecture §32 *Fase 7 — Autonomous PAPER*) is the first integration
point: Market Data → Graphiti memory → TradingAgents → QuantSignal → Signal
Fusion → TradeProposal → Risk Engine → OrderIntent → Nautilus paper execution →
Position → Close → TradeOutcome, operating unattended in PAPER mode and
recovering from restarts. ADR-0012 froze Redis Streams as the initial event bus
(INV-15); ADR-0007 froze NautilusTrader as the backtest/paper engine (INV-2);
INV-1 requires that a failed LLM analysis can never corrupt account state; INV-6
requires persisted write-before-send execution discipline.

Nothing before Phase 7 wired these together: `apps/worker` was an empty stub and
the canonical `DomainEvent` envelope had no transport.

## Decision

**Implement the pipeline as idempotent stages over one Redis Stream, with a
persisted run ledger as the idempotency backbone.**

1. **Transport (`apps/worker/bus.py`)** — one stream (`opentrading:events`,
   bounded with `MAXLEN`), one consumer group per stage
   (`opentrading-workers:<stage>`). Producers `XADD` the full envelope plus
   routing fields (`event_name`, `trace_id`); consumers `XREADGROUP` new
   messages and `XACK` on success. Every Redis command runs through a
   reconnect wrapper with exponential backoff (infinite retries in unattended
   mode), so a Redis outage pauses the pipeline instead of killing it.
   `InMemoryStreamBus` mirrors the same semantics for tests.

2. **Run ledger (`apps/worker/persistence.py`, migration `0004`)** — three
   tables: `pipeline_runs` (one row per `(trace_id, stage)` attempt), 
   `trade_lifecycles` (high-level trade lifecycle, CAS-guarded `version`), and
   `paper_accounts` (authoritative paper account, CAS-guarded). A stage whose
   run already SUCCEEDED is a no-op on redelivery; FAILED rows are replaced on
   retry. PostgreSQL access retries transient `OperationalError`s with
   `pool_pre_ping` + backoff (database reconnect).

3. **Worker restart recovery** — a worker first reclaims its group's PEL
   entries (`XPENDING` + `XAUTOCLAIM`) and dispatches them before reading new
   messages; combined with the run ledger this makes redelivery safe.
   Messages exceeding `max_deliveries` are ACKed and archived to a per-group
   dead-letter stream (never silently dropped, never replayed forever).

4. **Stage graph (`apps/worker/stages/`)** — ingest (scheduler: snapshot +
   `research.requested`), research (memory + TradingAgents + quant → one
   `ResearchBundle`), fusion, proposal (deterministic sizing: LLMs never
   size), risk (deterministic engine), order intent (UUIDv5 idempotency key
   over the decision), execution (Nautilus paper venue, SUBMITTED persisted
   before the venue call), positions (SL/TP close proposals through the same
   canonical chain), accounting (the *only* writer of `paper_accounts`), and
   posttrade (review + memory episode). Trace ids propagate through every
   envelope and payload.

5. **LLM failure containment** — any `TradingAgentsError` (timeout, crash,
   mapping) is caught inside the research stage, audited as
   `llm.analysis.failed`, and carried as `llm_error` on the bundle; fusion
   applies its missing-signal policy. With `llm_required` the cycle is
   skipped. Account state is only mutated by deterministic execution events —
   a failed LLM analysis cannot break it (INV-1).

6. **Paper venue (`adapters/nautilus/paper.py`)** — one-shot `BacktestEngine`
   per `OrderIntent` against the current `MarketSnapshot`, reusing the frozen
   mapping and cost models (INV-2). Instant fills synthesize the canonical
   ACKNOWLEDGED report. No real broker execution exists in this milestone:
   the execution stage refuses any mode other than PAPER.

## Consequences

- Full auditability: PostgreSQL alone reconstructs where any trace stopped;
  the stream's dead-letter archive preserves poisoned messages.
- The pipeline degrades gracefully under Redis/PostgreSQL/LLM outages and
  resumes unattended.
- Close orders flow through the same proposal → risk → intent chain as
  entries (one code path, INV-2); exit proposals are evaluated against the
  post-exit portfolio so closing never trips position-count limits.
- Multi-consumer groups and Langfuse tracing remain follow-up work.
