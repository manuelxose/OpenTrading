# Cross-Review Rules

Certain change classes automatically pull in mandatory reviewers, regardless of the
primary agent chosen. Reviewers are **additive**: the primary agent remains responsible
for the work.

| Change class | Automatic reviewers |
|---|---|
| **Risk-sensitive** — sizing, limits, exposure, leverage, margin, drawdown, daily loss, correlations, risk budgets, kill switches, orders, positions, portfolio, execution paths | `risk` + `verification` |
| **Execution-sensitive** — MT4 / MQL4, bridge, protocol, order transmission, broker interaction, reconciliation | `execution-mt4` + `risk` + `security` + `verification` |
| **Data-time semantics** — ingest, normalization, timestamps, `as_of` handling, snapshots, memory retrieval point-in-time behavior | `market-data` + `quant-research` + `verification` |
| **LLM-to-trading boundary** — TradingAgents, Graphiti retrieval, prompts feeding signals, signal fusion, any LLM output near capital decisions | `ai-trading-systems` + `risk` + `security` + `verification` |
| **Architecture-wide** — core/domain, event envelope, service decomposition, cross-service changes | `principal-architect` + `verification` |

## How to detect the change class

- Touches `engines/risk/`, sizing, limits, kill switch → risk-sensitive.
- Touches `mt4/`, `adapters/mt4/`, `QuantBridgeEA.mq4`, order protocol → execution-sensitive.
- Touches `data/`, `adapters/market_data/`, timestamps, snapshots, Graphiti temporal
  queries → data-time.
- Touches `adapters/tradingagents/`, `adapters/graphiti/`, `prompts/`, fusion weights →
  LLM-boundary.
- Touches `core/domain/`, `core/events/`, repository layout, new service → architecture-wide.

A change can be in several classes; union the reviewers.

## Escalation ladder

When reviewers disagree, escalate to `principal-architect`. Destructive or irreversible
actions (LIVE_AUTO changes, kill-switch changes, DB drops) additionally require a human
decision recorded in the task trail.

## Anti-patterns

- Reviewers who "approve" without running the checks → verification failure.
- Primary agent unilaterally dismissing a mandatory reviewer.
- Spawning the full team for single-file, non-sensitive edits.
