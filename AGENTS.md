# AGENTS.md — OpenTrading (Codex & generic agent adapters)

This repository has a canonical AI engineering layer under `.ai/`. This file is a thin
adapter: the source of truth lives there. Do not duplicate its rules here.

## Read first (cheap bootstrap)

- `.ai/README.md` — layer overview
- `.ai/rules/architecture-invariants.md` — INV-1..INV-16 (non-negotiable)
- `.ai/rules/definition-of-done.md` — completion gates
- `.ai/context/repo-map.md` — current repo state (PRE-00, docs only)

## Routing

Pick one primary specialist, then add the mandatory reviewers for the change class:

- Risk-sensitive → `risk` + `verification`
- Execution-sensitive → `execution-mt4` + `risk` + `security` + `verification`
- Data-time → `market-data` + `quant-research` + `verification`
- LLM-to-trading boundary → `ai-trading-systems` + `risk` + `security` + `verification`
- Architecture-wide → `principal-architect` + `verification`

Authoritative matrix: `docs/ai-engineering/ROUTING_RULES.md`.
Workflow: `.ai/workflows/task-routing.md`. Load agent cards from `.ai/agents/` and
skills from `.ai/skills/` only when needed.

## Context

Use Graphify first for codebase questions (see `docs/ai-engineering/CONTEXT_STRATEGY.md`).
Run `graphify update .` after material structural changes.

## Hard rules

- LLMs research, argue, propose. Deterministic code decides capital. Never weaken this.
- No RuFlo / Claude Flow / orchestration frameworks. Rule-based routing only.
- No trading functionality may be implemented during PRE-00.
- Substantial work ends with an adversarial Verification review
  (`.ai/workflows/verification-workflow.md`).
