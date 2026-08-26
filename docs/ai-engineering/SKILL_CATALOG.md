# Skill Catalog — OpenTrading

Skills are reusable procedures, not agents. Load one skill at a time, smallest relevant
body. Canonical bodies live under `.ai/skills/<category>/`.

## Index

| # | Skill | Purpose | Related agents |
|---|---|---|---|
| Repository intelligence ||||
| 1 | repository-navigation | find files/entry points via graph context | all |
| 2 | graphify-context | bounded subgraphs instead of re-reading repo | all |
| 3 | dependency-tracing | dependency direction and ripples | principal-architect, security |
| 4 | change-impact-analysis | blast radius + change class before editing | principal-architect, verification |
| Architecture ||||
| 5 | architecture-review | invariant-by-invariant design check | principal-architect, verification |
| 6 | adr-management | ADR lifecycle in docs/ADR/ | principal-architect |
| 7 | domain-boundary-review | core independent of external projects | principal-architect |
| 8 | event-contract-design | envelope + naming + versioning | principal-architect, backend-platform |
| 9 | state-machine-review | legal transitions + persistence | principal-architect, trading/risk/execution |
| Quant ||||
| 10 | point-in-time-validation | no look-ahead anywhere | market-data, quant-research, ai-trading-systems |
| 11 | backtest-validation | costs + determinism + OOS | quant-research, trading-backtest |
| 12 | walk-forward-validation | purged/embargoed temporal CV | quant-research, market-data |
| 13 | factor-evaluation | IC/RankIC, stability, decay, turnover | quant-research, market-data |
| 14 | model-evaluation | calibration, drift, robustness | quant-research, market-data |
| 15 | experiment-reproducibility | re-runnable experiments, full ledger | quant-research, verification |
| Trading ||||
| 16 | order-lifecycle-review | §9 state machine + idempotency | execution-mt4, trading-backtest, risk |
| 17 | execution-safety | no double-send / stale / over-send | execution-mt4, risk, security |
| 18 | reconciliation-review | DB vs broker convergence, SAFE_MODE | execution-mt4, risk |
| 19 | portfolio-risk-review | control coverage + bypass hunt | risk, verification |
| 20 | trading-cost-validation | realistic costs, post-cost alpha | trading-backtest, quant-research |
| AI systems ||||
| 21 | llm-agent-evaluation | §21 evaluation + Langfuse audit | ai-trading-systems, verification |
| Engineering ||||
| 22 | test-generation | right test type per layer | all, verification |
| 23 | debugging | root cause, not symptoms | all |
| 24 | performance-profiling | measure → fix → re-measure | backend-platform, infra-sre |
| 25 | refactoring | behavior-preserving simplification | backend-platform, principal-architect |
| 26 | dead-code-detection | remove unreachable/divergent paths | verification |
| 27 | api-contract-review | versioned contracts, both sides tested | backend-platform, execution-mt4, market-data |
| Security ||||
| 28 | threat-model | zones 1/2/3 attack paths | security |
| 29 | secret-scan | no secrets in git/memory/logs | security, infra-sre |
| 30 | dependency-security | pin + license + vuln review | security, principal-architect |
| 31 | privilege-boundary-review | least privilege LLM→Core→MT4 | security |
| Operations ||||
| 32 | observability-review | §23 dashboards/alerts + trace_id | infra-sre, ai-trading-systems |
| 33 | docker-review | reproducible least-privilege containers | infra-sre, security |
| 34 | production-readiness | Go/No-Go before deploys | infra-sre, security, verification |
| 35 | incident-analysis | safe recovery + postmortem | infra-sre |

## Detail

### 1–4 Repository intelligence
- **repository-navigation** — Triggers: "where is X". Inputs: symbol/path. Outputs:
  file list + path reasoning. Agents: all.
- **graphify-context** — Triggers: any codebase question beyond trivial edits. Inputs:
  question/symbols. Outputs: bounded subgraph. Agents: all.
- **dependency-tracing** — Triggers: cross-module changes, new deps. Inputs: module.
  Outputs: direction audit. Agents: principal-architect, security.
- **change-impact-analysis** — Triggers: domain/event/schema/risk-path changes. Inputs:
  planned diff. Outputs: affected modules, tests, reviewer set. Agents:
  principal-architect, verification.

### 5–9 Architecture
- **architecture-review** — Triggers: architecture-wide changes. Inputs: diff +
  invariants. Outputs: invariant verdicts. Agents: principal-architect, verification.
- **adr-management** — Triggers: frozen-decision/boundary decisions. Inputs: decision
  need. Outputs: ADR + index. Agent: principal-architect.
- **domain-boundary-review** — Triggers: domain/adapter changes. Inputs: diff.
  Outputs: boundary violations. Agent: principal-architect.
- **event-contract-design** — Triggers: new/changed events. Inputs: event + consumers.
  Outputs: schema + migration notes. Agents: principal-architect, backend-platform.
- **state-machine-review** — Triggers: state/transition changes. Inputs: state diff.
  Outputs: transition audit. Agents: principal-architect + trading/risk/execution.

### 10–15 Quant
- **point-in-time-validation** — Triggers: ingest, snapshots, retrieval, backtest
  inputs. Inputs: code + clock semantics. Outputs: violations + required leakage tests.
  Agents: market-data, quant-research, ai-trading-systems.
- **backtest-validation** — Triggers: backtest creation/claims. Inputs: config + data
  hash + results. Outputs: validity verdict. Agents: quant-research, trading-backtest.
- **walk-forward-validation** — Triggers: temporal model training/CV. Inputs: splits.
  Outputs: leakage audit. Agents: quant-research, market-data.
- **factor-evaluation** — Triggers: factor add/change. Inputs: implementation +
  evaluation config. Outputs: IC/RankIC + decay report. Agents: quant-research,
  market-data.
- **model-evaluation** — Triggers: model train/compare/promote. Inputs: artifacts +
  config. Outputs: metrics + drift report. Agents: quant-research, market-data.
- **experiment-reproducibility** — Triggers: experiment claims/promotions. Inputs:
  experiment code. Outputs: reproducibility verdict. Agents: quant-research,
  verification.

### 16–20 Trading
- **order-lifecycle-review** — Triggers: order state/persistence changes. Inputs: diff.
  Outputs: transition + idempotency audit. Agents: execution-mt4, trading-backtest,
  risk.
- **execution-safety** — Triggers: EA/bridge/protocol changes. Inputs: diff +
  protocol. Outputs: safety findings. Agents: execution-mt4, risk, security.
- **reconciliation-review** — Triggers: reconciliation/restart changes. Inputs: diff.
  Outputs: divergence-handling audit. Agents: execution-mt4, risk.
- **portfolio-risk-review** — Triggers: sizing/limits/kill-switch changes. Inputs:
  diff + policy. Outputs: control coverage + bypass findings. Agents: risk,
  verification.
- **trading-cost-validation** — Triggers: cost models/backtest economics. Inputs:
  cost model + config. Outputs: realism verdict. Agents: trading-backtest,
  quant-research.

### 21 AI systems
- **llm-agent-evaluation** — Triggers: prompts/providers/retrieval changes. Inputs:
  diff + eval dataset. Outputs: §21 report. Agents: ai-trading-systems, verification.

### 22–27 Engineering
- **test-generation** — Triggers: any logic change. Inputs: code + invariants.
  Outputs: tests + evidence. Agents: all.
- **debugging** — Triggers: failures. Inputs: failure + trace_id. Outputs: root cause
  + regression test. Agents: all.
- **performance-profiling** — Triggers: latency/throughput issues. Inputs: profile
  data. Outputs: fix + before/after. Agents: backend-platform, infra-sre.
- **refactoring** — Triggers: complexity/duplication. Inputs: module + coverage.
  Outputs: diff + green tests. Agents: backend-platform, principal-architect.
- **dead-code-detection** — Triggers: reviews/refactors. Inputs: tree. Outputs:
  dead-code list. Agent: verification.
- **api-contract-review** — Triggers: any contract change. Inputs: diff. Outputs:
  compatibility verdict. Agents: backend-platform, execution-mt4, market-data.

### 28–31 Security
- **threat-model** — Triggers: new components/paths/zones. Inputs: design + flows.
  Outputs: threat list in docs/threat-model/. Agent: security.
- **secret-scan** — Triggers: pre-commit/review. Inputs: changed files. Outputs:
  findings + remediation. Agents: security, infra-sre.
- **dependency-security** — Triggers: dep add/bump. Inputs: dep + version. Outputs:
  pinning + risk verdict. Agents: security, principal-architect.
- **privilege-boundary-review** — Triggers: authn/z/zone changes. Inputs: permission
  design. Outputs: privilege audit. Agent: security.

### 32–35 Operations
- **observability-review** — Triggers: instrumentation/alerts. Inputs: component +
  dashboards. Outputs: coverage gaps. Agents: infra-sre, ai-trading-systems.
- **docker-review** — Triggers: compose/Dockerfile changes. Inputs: diff. Outputs:
  findings. Agents: infra-sre, security.
- **production-readiness** — Triggers: deploys/phase gates. Inputs: release + runbooks.
  Outputs: Go/No-Go. Agents: infra-sre, security, verification.
- **incident-analysis** — Triggers: failures/SAFE_MODE. Inputs: alerts/logs/traces.
  Outputs: timeline + postmortem. Agent: infra-sre.
