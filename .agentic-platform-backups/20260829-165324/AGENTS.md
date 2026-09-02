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

<!-- BEGIN AGENTIC-ENGINEERING-PLATFORM -->
# Managed engineering policy

Use repository evidence before assumptions. For codebase, architecture, dependency, or data-flow questions, query Graphify first when `graphify-out/graph.json` exists; use its scoped query/path/explain output to identify the smallest relevant file set. Do not bulk-read generated graph artifacts.

For non-trivial changes: understand → graph discovery → plan → implement narrowly → test → independent review when practical → verify. Preserve repository architecture and unrelated working-tree changes. Select skills and a focused specialist only when they materially help; do not create persistent swarms.

Never hardcode secrets, providers, credentials, or machine-local assumptions. Never claim a check passed unless it was executed. Keep context lean without skipping security, migrations, dependency inspection, or validation. Refresh Graphify after material structural changes.

For UI work, use the existing design system and assess responsive layouts, keyboard/focus behavior, accessibility, loading/empty/error/success states, and light/dark themes where supported. Do not present placeholders or fake metrics as working product behavior.
<!-- END AGENTIC-ENGINEERING-PLATFORM -->
