# Repository Map (OpenTrading)

Current state: **PRE-00**. The repository holds only `docs/architecture.md` (Spanish) —
the definitive product architecture — plus this AI engineering layer. No code, no
packages, no git history yet.

## Canonical sources of truth

| Doc | Purpose |
|---|---|
| `docs/architecture.md` | Product architecture (§1–§35): vision, components, modes, risk engine, MT4, reconciliation, memory, data, events, domain objects, fusion, post-trade, strategy factory, metrics, LLM eval, observability, Graphify, Obsidian, security, testing, roadmap, frozen decisions |
| `docs/ai-engineering/AGENT_ARCHITECTURE.md` | AI team topology |
| `docs/ai-engineering/ROUTING_RULES.md` | Task → agent routing |
| `.ai/rules/architecture-invariants.md` | INV-1..INV-16 non-negotiables |

## Target repository layout (architecture §27, to be created in Phase 0)

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
