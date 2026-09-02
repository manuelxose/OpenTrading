# OpenTrading — GitHub Copilot instructions

Thin adapter to the canonical AI engineering layer under `.ai/`. The source of truth
lives there and in `docs/ai-engineering/`; do not duplicate its rules in this file.

## Always start here

- `.ai/README.md` — layer overview
- `.ai/rules/architecture-invariants.md` — INV-1..INV-16 (non-negotiable)
- `.ai/rules/definition-of-done.md` — completion gates
- `.ai/context/repo-map.md` — current repo state (PRE-00: docs only, no code yet)

## Routing (do not wait for the user to name an agent)

Pick one primary specialist from `.ai/agents/`, then add mandatory reviewers for the
change class (`.ai/rules/cross-review-rules.md`, matrix in
`docs/ai-engineering/ROUTING_RULES.md`):

- Risk-sensitive → `risk` + `verification`
- Execution-sensitive → `execution-mt4` + `risk` + `security` + `verification`
- Data-time semantics → `market-data` + `quant-research` + `verification`
- LLM-to-trading boundary → `ai-trading-systems` + `risk` + `security` + `verification`
- Architecture-wide → `principal-architect` + `verification`

One primary per task. Do not spawn the whole team for small edits.

## Context

Use Graphify first for codebase questions (`graphify query` / `path` / `explain`);
run `graphify update .` after material structural changes. See
`docs/ai-engineering/CONTEXT_STRATEGY.md`.

## Hard rules

- LLMs research, argue, propose. Deterministic code decides capital. Never weaken this.
- Point-in-time correctness everywhere; risk engine deterministic; MT4 execution-only.
- No RuFlo / Claude Flow / orchestration frameworks. Rule-based routing only.
- No trading functionality may be implemented during PRE-00.
- Substantial work ends with an adversarial Verification review
  (`.ai/workflows/verification-workflow.md`, report via
  `.ai/templates/review-report.md`).

## Reporting

Implementation agents report via `.ai/templates/agent-output.md` (Goal, Repository
evidence, Files affected, Implementation, Tests, Risks, Remaining issues).

<!-- BEGIN AGENTIC-ENGINEERING-PLATFORM -->
Use repository evidence before assumptions. When `graphify-out/graph.json` exists, query Graphify before broad repository exploration; determine impacted files, callers, dependencies, and data flows, then read only the minimum relevant source. Never ingest graph artifacts wholesale.

For non-trivial work: understand → graph discovery → plan → implement narrowly → test → review → verify. Preserve unrelated behavior and existing instructions. Do not hardcode secrets, providers, credentials, or environment-specific values. Do not invent repository behavior or claim checks passed unless executed. Keep token use lean, but never skip correctness, security, migrations, or critical dependency inspection. For UI changes, verify responsive behavior, accessibility, and all interaction states.
<!-- END AGENTIC-ENGINEERING-PLATFORM -->
