# Gap Analysis — Current vs Target Architecture

- **Date:** 2026-08-26
- **Method:** compare `docs/architecture/CURRENT_STATE.md` (verified repository evidence)
  against `docs/architecture.md` §1–§35 (target) and `docs/architecture/TARGET_ARCHITECTURE.md`.
- **Overall finding:** the repository is at **PRE-00** (docs-only). Governance and target
  design are complete; **100% of runtime implementation is missing**. The gap is therefore
  uniform "not started" per component, with a short list of documentation-level gaps.

## 1. Component-by-component gap

| # | Target component | Target (§) | Current state | Gap | Closing milestone |
|---|---|---|---|---|---|
| 1 | Monorepo layout (apps/core/engines/adapters/…) | 27 | Absent | No directories, no packages | Phase 0 |
| 2 | Domain model + Pydantic schemas (canonical objects) | 15 | Absent (vocabulary only, in `.ai/context/domain-glossary.md`) | No `core/domain`, no schemas | Phase 0 |
| 3 | Virtual clock + event envelope | 12, 14 | Absent | No `core/clock`, no `core/events` | Phase 0 |
| 4 | Configuration + `.env.example` + Makefile | 27, 29 | Absent (only `.gitignore` policy) | No runtime config | Phase 0 |
| 5 | CI | 32 (Phase 0) | Absent | No CI definition | Phase 0 |
| 6 | PostgreSQL + TimescaleDB (transactional truth) | 13 | Absent | No database, no migrations | Phase 1 |
| 7 | Parquet + MinIO (heavy history, medallion) | 13 | Absent | No object storage, no catalogs | Phase 1 |
| 8 | Redis (cache, locks, Streams) | 13, 14 | Absent | No event bus | Phase 1 |
| 9 | Market data normalization + PIT snapshots + quality | 12, 13 | Absent | No adapters/market_data, no `MarketSnapshot` | Phase 1 |
| 10 | TradingAgents adapter (LLMSignal) | 3 | Absent | No `adapters/tradingagents`, no prompts | Phase 2 |
| 11 | Graphiti temporal memory (ontology, episodes, `as_of`) | 11, 12 | Absent | No FalkorDB, no `adapters/graphiti` | Phase 3 |
| 12 | NautilusTrader adapter (backtest/paper, deterministic) | 5 | Absent | No `adapters/nautilus`, no venues | Phase 4 |
| 13 | Risk Engine + Policy Engine (deterministic) | 7 | Absent | No `engines/risk` — the single most critical missing component | Phase 5 |
| 14 | Kill switches / dead-man switch | 10 | Absent | Policy documented only | Phase 5 (+7) |
| 15 | MT4 bridge (QuantBridgeEA.mq4, ZeroMQ gateway, protocol) | 8 | Absent | No `mt4/`, no `adapters/mt4` | Phase 6 |
| 16 | Reconciliation + SAFE_MODE + order state machine | 9 | Absent | State machine documented only | Phase 6/7 |
| 17 | Signal Fusion Engine | 16 | Absent | No `engines/signal_fusion`; weights uncalibrated (must come from validation) | Phase 7 |
| 18 | Post-trade learning loop | 17 | Absent | No `engines/posttrade` | Phase 7 |
| 19 | Quant Factory (RD-Agent, Qlib, MLflow) | 4 | Absent | No `services/quant-rd`, no `adapters/qlib|rdagent` | Phase 9 |
| 20 | Validation Factory + promotion lifecycle | 18, 19 | Absent | No `engines/promotion` | Phase 10 |
| 21 | Command Center (TypeScript UI) | 26 | Absent | No `apps/command-center` | Phase 7+ (UI tracks capability availability) |
| 22 | Observability: Langfuse | 22 | Absent | No tracing | Phase 2+ |
| 23 | Observability: Prometheus + Grafana | 23 | Absent | No metrics, no alerts | Phase 1+ |
| 24 | Obsidian vaults | 25 | Absent | No `vault-trading/` | Phase 7 |
| 25 | `external-lock.yaml` dependency pinning | 28 | Absent | INV-14 unmet until first dependency lands | Phase 0/1 |
| 26 | Tests (unit/property/integration/replay/leakage/chaos) | 30 | Absent | No `tests/` | Phase 0 (harness), continuously thereafter |
| 27 | Secrets handling (SOPS+age / Vault) | 29 | Policy only | No runtime secret store; `.gitignore` policy in place | Phase 6 (first broker credentials) |

## 2. Documentation-level gaps (closed or remaining)

| Item | Status |
|---|---|
| ADRs for frozen decisions | **Closed by this task** — 16 ADRs in `docs/ADR/` |
| `docs/architecture/{CURRENT_STATE,TARGET_ARCHITECTURE,GAP_ANALYSIS,IMPLEMENTATION_ORDER}.md` | **Closed by this task** |
| `docs/ADR/README.md` index | **Closed by this task** |
| `docs/threat-model/` | Open — target §27; due before Phase 6 (MT4 bridge) |
| `docs/runbooks/`, `docs/protocols/` | Open — due with Phases 5–6 |
| Graphify graph population | Expected empty until code lands (verified: 0 code nodes) — not a defect |

## 3. Where the repository is AHEAD of the target

| Area | Evidence |
|---|---|
| Architecture invariants | INV-1…INV-16 exist as enforceable review criteria before any code |
| AI engineering governance | 12 agents, 35 skills, routing matrix, DoD, adversarial Verification workflow — all pre-date Phase 0 |
| Test discipline specification | §30 + DoD gates (property-based, leakage, replay, chaos) specified before implementation |
| Secrets policy | `.gitignore` + §29 trust zones already codified; no secrets have ever been committed |

## 4. Structural risks of the gap

1. **Ambiguity risk (low):** frozen decisions are already enumerated (§34) and now ADR'd;
   drift is mitigated by INV-12 and the ADR workflow.
2. **Look-ahead/leakage risk (future):** highest-probability failure mode in this domain.
   Mitigation is specified (INV-3, leakage tests) but unproven until Phase 1–4 land.
3. **LLM-authority risk (future):** mitigated by design (INV-1, INV-4, INV-5); must be
   enforced in code review from the first line of Phase 2.
4. **Divergent backtest/paper/live implementations (future):** mitigated by INV-2
   (`OrderIntent` as the single crossing object).
5. **Execution risk today: none** — no code, no broker connection, no credentials exist.

## 5. Verdict

The gap is total for implementation and nearly closed for design and governance.
The correct next action is **Phase 0 (Foundations)** executed in the order defined by
`docs/architecture/IMPLEMENTATION_ORDER.md`. No trading feature may start before the
Phase 0 definition of done holds.
