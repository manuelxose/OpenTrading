# Routing Rules — OpenTrading

Authoritative task → agent routing. The developer should not normally need to name
agents; apply the matrix below. Workflow: `.ai/workflows/task-routing.md`.

## Change classes → mandatory reviewers

From `.ai/rules/cross-review-rules.md`:

| Change class | Mandatory reviewers |
|---|---|
| Risk-sensitive (sizing, limits, exposure, drawdown, orders, positions, portfolio, execution paths) | `risk` + `verification` |
| Execution-sensitive (MT4/MQL4, bridge, protocol, broker interaction) | `execution-mt4` + `risk` + `security` + `verification` |
| Data-time semantics (ingest, timestamps, `as_of`, snapshots, memory retrieval) | `market-data` + `quant-research` + `verification` |
| LLM-to-trading boundary (TradingAgents, Graphiti retrieval, prompts, fusion) | `ai-trading-systems` + `risk` + `security` + `verification` |
| Architecture-wide (domain, envelope, service decomposition) | `principal-architect` + `verification` |

Union the reviewer sets when a task belongs to multiple classes.

## Primary-agent matrix

| Task type | Primary | Supporting | Notes |
|---|---|---|---|
| Qlib factor / model / experiment | `quant-research` | `market-data` | costs → `trading-backtest` |
| RD-Agent integration / candidate factory | `quant-research` | `ai-trading-systems` if LLM-facing | never touches risk limits or production |
| Market data ingest / schemas / snapshots | `market-data` | `backend-platform` | PIT tests mandatory |
| Backtest engine / paper trading / fills | `trading-backtest` | `risk`, `execution-mt4` (parity) | determinism tests mandatory |
| Position sizing / risk limits / kill switch | `risk` | `trading-backtest` | property tests mandatory |
| MT4 / MQL4 / bridge / protocol | `execution-mt4` | `risk`, `backend-platform` | idempotency + reconciliation tests |
| Graphiti / TradingAgents / prompts / fusion | `ai-trading-systems` | `market-data`, `quant-research` | no LLM execution path |
| API / workers / Redis Streams / Postgres | `backend-platform` | `market-data` (schema) | event envelope mandatory |
| Command Center UI | `command-center` | `backend-platform` (API contracts) | proportional UI review |
| Docker / deploy / observability / backups | `infra-sre` | `security` | exposure review |
| Secrets / authn / threat model / dependencies | `security` | `infra-sre` | zone review |
| Cross-cutting architecture / ADRs | `principal-architect` | affected domain agents | ADR if frozen decisions involved |
| Review of completed substantial work | `verification` | domain agents consulted | adversarial only |

## Anti-routing rules

- Do not spin the full team for single-file, non-sensitive edits.
- Do not let an LLM-facing agent own execution paths.
- Do not let any agent other than `risk` (primary) modify risk logic without
  `risk` review.
- Verification never implements; it reviews.
- If the change class is ambiguous, escalate to `principal-architect` before coding.

## Examples (canonical)

| Scenario | Primary | Supporting | Mandatory reviewers |
|---|---|---|---|
| Modify a Qlib factor | `quant-research` | `market-data` | `verification` (+data-time if timestamps touched) |
| Change position sizing | `risk` | `trading-backtest` | `verification` |
| Modify an MT4 order path | `execution-mt4` | `risk` | `security` + `verification` |
| Change Graphiti retrieval | `ai-trading-systems` | `market-data` | `verification` (+ `risk`, `security` if signal-boundary) |
| New dashboard screen | `command-center` | `backend-platform` (if API changes) | `verification` (substantial) |
| Change PostgreSQL schema | `backend-platform` | `market-data` | `principal-architect` (domain contracts) + `verification` |
| Diagnose poor backtest performance | `trading-backtest` | `quant-research` | `verification` |
| Broker reconciliation failure | `execution-mt4` | `backend-platform` | `risk` + `security` + `verification` |
| Change TradingAgents prompts | `ai-trading-systems` | `market-data` | `risk` + `security` + `verification` |
| System-wide architecture change | `principal-architect` | affected domains | `verification` |

Full scenario validation: `docs/ai-engineering/VALIDATION.md`.
