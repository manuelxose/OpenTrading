# .ai — Canonical AI Engineering Layer (OpenTrading)

Vendor-neutral source of truth for the repository-specific AI engineering team of the
Autonomous Quantitative Trading & Research Platform.

This layer is **canonical**. Tool-specific adapters (Codex, Claude Code, Cursor, Copilot)
must stay thin and point here instead of duplicating knowledge.

## Hard boundary (never changes)

> LLMs research, argue and propose. Deterministic code decides whether a trade may execute.

See `.ai/rules/architecture-invariants.md` for the full invariant set derived from
`docs/architecture.md`.

## Layout

```text
.ai/
├── README.md              # this file
├── agents/                # 12 specialist agents (purpose, scope, triggers, forbidden actions)
├── skills/                # 35 reusable procedural skills, grouped by domain
├── rules/                 # architecture invariants, Definition of Done, cross-review, context
├── workflows/             # task routing, ADR, adversarial verification
├── context/               # repo map + domain glossary (cheap context bootstrap)
└── templates/             # agent output, review report, ADR
```

## Agents (one primary per task by default)

| Agent | Domain |
|---|---|
| `principal-architect` | boundaries, ADRs, event contracts, anti-drift |
| `quant-research` | Qlib / RD-Agent, factors, models, leakage-free validation |
| `market-data` | PIT data, normalization, Parquet/MinIO/Timescale |
| `trading-backtest` | NautilusTrader, fills/costs, BACKTEST/PAPER/LIVE parity |
| `risk` | deterministic Risk Engine, limits, kill switches |
| `execution-mt4` | MQL4 bridge, protocol, idempotency, reconciliation |
| `ai-trading-systems` | TradingAgents, Graphiti, prompts, Langfuse |
| `backend-platform` | FastAPI, workers, Redis Streams, Postgres |
| `command-center` | TypeScript dashboard, visualization |
| `infra-sre` | Docker, observability, backups, reliability |
| `security` | trust zones, secrets, broker boundary |
| `verification` | adversarial independent review |

## Routing

1. Classify the task and its change class (risk-sensitive, execution-sensitive,
   data-time, LLM-boundary, architecture-wide) — `.ai/rules/cross-review-rules.md`.
2. Pick the **primary** specialist from `docs/ai-engineering/ROUTING_RULES.md`.
3. Add the **mandatory reviewers** for that change class.
4. Load only the skills owned by those agents.
5. Execute under `.ai/rules/definition-of-done.md`; substantial work ends with a
   Verification review.

Do not spin up the whole team for small tasks. One primary agent by default.

## Tool adapters

- Codex / generic agents → `AGENTS.md`
- Claude Code → `CLAUDE.md`
- Cursor → `.cursor/rules/00-canonical.mdc`
- GitHub Copilot → `.github/copilot-instructions.md`

## Governance notes

- No RuFlo / Claude Flow / heavy orchestration frameworks. Routing is rule-based.
- No trading feature may be implemented under PRE-00. This layer is documentation + config only.
- Full architecture of the AI team: `docs/ai-engineering/AGENT_ARCHITECTURE.md`.
