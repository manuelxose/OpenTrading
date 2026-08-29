# Repository Map (OpenTrading)

Current state: **Phase 0 — Foundations implemented** (2026-08-26). The monorepo now
matches the §27 target layout: canonical Pydantic contracts (`core/schemas`), domain
enums + state machines (`core/domain`), event envelope + registry (`core/events`),
virtual clock (`core/clock`), settings (`core/config`), audit (`core/audit`), and the
`apps/`, `engines/`, `adapters/`, `services/`, `research/`, `infra/` skeleton.
External trading framework integrations (Phases 1–12) are phase-gated; of these,
the TradingAgents LLM committee (Phase 2) is now integrated **read-only** behind
`adapters/tradingagents` (`MarketSnapshot → ResearchRequest → LLMSignal`, ADR-0004,
pinned upstream v0.3.1) — see `adapters/tradingagents/README.md`.
See `docs/architecture/PHASE0_FOUNDATIONS.md` for the Phase 0 implementation record.

## Canonical sources of truth

| Doc | Purpose |
|---|---|
| `docs/architecture.md` | Product architecture (§1–§35): vision, components, modes, risk engine, MT4, reconciliation, memory, data, events, domain objects, fusion, post-trade, strategy factory, metrics, LLM eval, observability, Graphify, Obsidian, security, testing, roadmap, frozen decisions |
| `docs/architecture/CURRENT_STATE.md` | Verified repository state (audit PRE-00 + Phase 0 addendum) |
| `docs/architecture/PHASE0_FOUNDATIONS.md` | What Phase 0 implemented: modules, contracts, clock, events, tests, DoD evidence |
| `docs/architecture/TARGET_ARCHITECTURE.md` | English condensation of `docs/architecture.md` (never drifts from it) |
| `docs/architecture/GAP_ANALYSIS.md` | Component-by-component gap vs target, with closing milestones |
| `docs/architecture/IMPLEMENTATION_ORDER.md` | Phase dependency graph and ordering (Phases 0–12) |
| `docs/ADR/` | 16 ADRs for the frozen decisions (§34) + index README |
| `docs/ai-engineering/AGENT_ARCHITECTURE.md` | AI team topology |
| `docs/ai-engineering/ROUTING_RULES.md` | Task → agent routing |
| `.ai/rules/architecture-invariants.md` | INV-1..INV-16 non-negotiables |

## Target repository layout (architecture §27 — created in Phase 0)

```text
apps/         api, worker, command-center
core/         domain, schemas, events, config, clock, audit
engines/      signal_fusion, risk, portfolio, posttrade, promotion
adapters/     tradingagents, graphiti, nautilus, qlib, rdagent, market_data, mt4
services/     core-runtime (Py 3.12), quant-rd (Py 3.11 Linux)
mt4/          Experts/QuantBridgeEA.mq4, Include, protocol, tests
research/     factors, models, strategies, baselines, notebooks
data/         schemas, catalogs, fixtures
prompts/      analysts, researchers, trader, evaluators
infra/        compose, postgres, redis, falkordb, minio, mlflow, langfuse, prometheus, grafana
vault-trading/ (Obsidian, not committed to git with secrets)
tests/        unit, integration, replay, leakage, backtest, execution, risk, security, chaos
docs/         architecture, ADR, threat-model, runbooks, protocols, ai-engineering
graphify-out/ graph.json, wiki/, GRAPH_REPORT.md (committed; cache/ ignored)
```

## Key facts for agents

- Backend: Python. Core runtime 3.12; Quant R&D (RD-Agent/Qlib) 3.11 Linux. Never merged.
- Frontend: TypeScript Command Center.
- Broker: MetaTrader 4 via private ZeroMQ bridge; MQL4 stays dumb.
- Event bus: Redis Streams (Kafka later).
- Observability: Langfuse (AI) + Prometheus/Grafana (ops).
- Dependencies pinned in `external-lock.yaml`; production never follows main/latest/HEAD.
- No RuFlo/Claude Flow/orchestration frameworks. Rule-based routing in `.ai/`.

## Domain glossary

See `.ai/context/domain-glossary.md`.
