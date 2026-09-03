# OpenTrading — Autonomous Quantitative Trading & Research Platform

A personal, autonomous, auditable, evolvable quantitative firm: research strategies,
validate them, paper-trade, and finally execute via MetaTrader 4 — **without granting any
LLM direct control over capital**.

> **LLMs research, argue and propose. Deterministic code decides whether a trade may execute.** (INV-1)

## Status

- **Phase 0 — Foundations: implemented** (this repository state).
  See `docs/architecture/PHASE0_FOUNDATIONS.md`.
- **Phase 1 — Data Platform: implemented** — local infrastructure
  (PostgreSQL/TimescaleDB, Redis, MinIO, FalkorDB, MLflow, Langfuse,
  Prometheus, Grafana via Docker Compose) **and** the market data platform:
  medallion pipeline `RAW → BRONZE → SILVER → GOLD → MarketSnapshot` with
  strict point-in-time semantics (three timestamps per record, immutable
  hash-sealed gold versions, single INV-3 filter choke point).
  See `docs/architecture/PHASE1_DATA_PLATFORM.md`, `docs/ADR/0017` and
  `docs/runbooks/local-development.md`.
- **Phase 5 — Risk Engine: implemented** — the deterministic Risk & Policy
  Engine (`engines/risk`, INV-4): 24 controls (hard rejections + soft
  resizing), `APPROVE | RESIZE | REJECT` with deterministic reason codes,
  engine-computed quantities only (INV-1), exact-arithmetic size gate.
  See `docs/architecture/PHASE5_RISK_ENGINE.md`, `docs/ADR/0015` and
  `docs/ADR/0018`.
- **Phase 6 — MT4 protocol + emulator: implemented** — the versioned MT4
  execution protocol (ADR-0020): private ZeroMQ (REQ/REP, PUSH/PULL,
  PUB/SUB), 13-message vocabulary, idempotency/duplicate detection, sequence
  validation, command expiration, schema + checksum validation, connection
  health, structured error codes — plus the Python MT4 emulator
  (`adapters/mt4/`) against which the Core executes the full lifecycle with
  no MetaTrader installed (Phase 6 DoD: the same `order_intent_id` 100× never
  generates more than one trade). `QuantBridgeEA.mq4` is the next step.
  See `mt4/protocol/README.md`, `docs/ADR/0020`.
- **Execution state + reconciliation + Safe Mode: implemented** — the INV-6
  guarantee (`send_order() != executed_trade`): authoritative execution state
  persisted in PostgreSQL (`execution_orders`, `execution_positions`,
  `reconciliation_runs`, `safe_mode_state`), SUBMITTED written *before* the
  wire send, duplicate-fill fingerprints, fill-before-ACK synthesis, and the
  mandatory §9 restart reconciliation (open orders, positions, quantities,
  identifiers) with EXPLAINABLE auto-healing. Material unexplained divergence
  → SAFE_MODE (new positions blocked; monitoring, reconciliation and
  risk-reducing actions allowed; event + audit + alert). DoD: crash after
  submit, crash before ACK, duplicate fill, out-of-order events, MT4 restart,
  network partition, manual broker position.
  See `docs/architecture/PHASE7_EXECUTION_STATE.md`, `docs/ADR/0021`.
- **Emergency control system (INV-7): implemented** — the four levels
  STRATEGY_KILL / INSTRUMENT_KILL / NO_NEW_POSITIONS / EMERGENCY_KILL
  (cancel pending + block entries + flatten only when explicitly configured)
  and the dead man switch: Core ↔ MT4 heartbeat loss keeps broker-side SL/TP,
  blocks new entries, raises a CRITICAL alert and enters a persisted safe
  execution state — positions are never auto-closed by connectivity loss
  unless the policy explicitly requires it. Every action is audited, emitted
  as a domain event and exposed through the operator API + a cron-able
  `check-emergency` monitor; the controller is fully independent of LLM and
  strategy processes.
  See `engines/execution/emergency.py`, `docs/ADR/0024`.
- Phases 2–12 (TradingAgents, Graphiti, Nautilus, MT4 EA, paper trading,
  LIVE, Quant Factory, promotion) are **implemented** (the statement below is
  superseded). See the canonical status documents:
  `docs/PRODUCTION_READINESS.md` (audited 2026-08-29), `docs/KNOWN_LIMITATIONS.md`,
  `docs/OPERATIONS_MANUAL.md` and `docs/DISASTER_RECOVERY.md`. The MT4 EA
  (`QuantBridgeEA.mq4`) and the production live-intent wiring remain the only
  outstanding Phase 8 items; no live capital has ever been connected.

## Canonical documents

| Document | Purpose |
|---|---|
| `docs/architecture.md` | Canonical target architecture (Spanish, authoritative) |
| `docs/architecture/TARGET_ARCHITECTURE.md` | English reference condensation |
| `docs/architecture/IMPLEMENTATION_ORDER.md` | Phase plan and gates |
| `docs/architecture/PHASE0_FOUNDATIONS.md` | What is implemented here |
| `docs/architecture/PHASE1_DATA_PLATFORM.md` | Market data platform record (Phase 1) |
| `docs/architecture/PHASE5_RISK_ENGINE.md` | Deterministic Risk Engine record (Phase 5) |
| `docs/architecture/PHASE7_EXECUTION_STATE.md` | Broker reconciliation & Safe Mode record (INV-6) |
| `docs/PRODUCTION_READINESS.md` | Production-readiness audit, verdict and open gates |
| `docs/GUIA_INSTALACION_USO.md` | Guía completa de instalación y uso desde cero (español) |
| `docs/KNOWN_LIMITATIONS.md` | Classified limitations (BLOCKING/MAJOR/MINOR/INFO) |
| `docs/OPERATIONS_MANUAL.md` | How to run, monitor and operate every mode |
| `docs/DISASTER_RECOVERY.md` | RPO/RTO targets, backups, restore and incident playbooks |
| `docs/ADR/` | Frozen decisions (26 ADRs) |
| `.ai/rules/architecture-invariants.md` | Non-negotiable invariants INV-1…INV-16 |
| `docs/strategy/XAUUSD_RPB_SPEC.md` | Frozen XAU_RPB strategy contract (`XAU_RPB_V1.0.0`) |
| `docs/strategy/RESEARCH_REPORT.md` | XAU_RPB qualification status and limitations |
| `docs/strategy/VALIDATION_METHODOLOGY.md` | How XAU_RPB would be proven or rejected |
| `docs/strategy/RISK_POLICY.md` | XAU_RPB risk mandate and kill switches |
| `docs/strategy/BROKER_COMPATIBILITY.md` | XAUUSD-specific broker audit |
| `docs/runbooks/xau-rpb-ea.md` | Installing and operating the XAU_RPB EA |

## Repository layout (per `docs/architecture.md` §27)

```text
apps/            api (FastAPI, health + contract catalog), worker, command-center (TS)
core/            domain (enums, state machines), schemas, events, config, clock, audit
engines/         signal_fusion, risk, execution, portfolio, posttrade, promotion
                 (phase-gated)
adapters/        tradingagents, graphiti, nautilus, qlib, rdagent,
                 market_data, mt4                                       (phase-gated)
services/        core-runtime (Python 3.12), quant-rd (Python 3.11)
research/        factors, models, strategies (xau_rpb), validation,
                 baselines, notebooks
infra/           compose + per-service config (postgres, redis, minio, …)
mt4/             QuantBridgeEA.mq4 (Phase 6, execution-only, INV-5)
                 XauRpbEA.mq4 + Include/xau_rpb/ (standalone EA, ADR-0027)
tests/           unit, integration, replay, leakage, backtest, execution,
                 risk, security, chaos
```

## Development

```bash
make setup      # uv sync --all-groups (Python 3.12)
make lint       # ruff
make typecheck  # mypy (strict)
make test       # pytest
make ci         # all gates
```

- The domain layer (`core/`) imports **no external trading framework**
  (TradingAgents, MT4, Qlib, Graphiti, Nautilus) — enforced by a unit test.
- No production component may call `datetime.now()` for domain decisions — use
  `core.clock.Clock` (`SystemClock` / `VirtualClock`).
- `OrderIntent` is the only canonical object that crosses the system (INV-2).
