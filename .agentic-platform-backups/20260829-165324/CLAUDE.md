# CLAUDE.md — OpenTrading (Claude Code adapter)

This is a thin adapter to the canonical AI engineering layer in `.ai/`.
Source of truth: `.ai/` and `docs/ai-engineering/`.

## Bootstrap (read before working)

1. `.ai/README.md`
2. `.ai/rules/architecture-invariants.md` (INV-1..INV-16 — non-negotiable)
3. `.ai/rules/cross-review-rules.md` + `docs/ai-engineering/ROUTING_RULES.md`
4. `.ai/context/repo-map.md` (repo is PRE-00: docs only, no code yet)

## Working rules

- Route every task: one primary specialist from `.ai/agents/` + mandatory reviewers
  for the change class. Do not spawn the full team.
- Graphify first for codebase questions; `graphify update .` after structural changes.
- Definition of Done: `.ai/rules/definition-of-done.md`. Substantial work requires an
  adversarial Verification review.
- Invariants: LLMs never gain authority over capital (INV-1); MT4 stays dumb (INV-5);
  point-in-time everywhere (INV-3); risk is deterministic (INV-4).
- No RuFlo / Claude Flow / swarms. No trading features during PRE-00.

## Report

Implementation agents report via `.ai/templates/agent-output.md`;
Verification via `.ai/templates/review-report.md`.

<!-- BEGIN AGENTIC-ENGINEERING-PLATFORM -->
# Managed engineering policy

Use repository evidence before assumptions. For codebase, architecture, dependency, or data-flow questions, query Graphify first when `graphify-out/graph.json` exists; use its scoped query/path/explain output to identify the smallest relevant file set. Do not bulk-read generated graph artifacts.

For non-trivial changes: understand → graph discovery → plan → implement narrowly → test → independent review when practical → verify. Preserve repository architecture and unrelated working-tree changes. Select skills and a focused specialist only when they materially help; do not create persistent swarms.

Never hardcode secrets, providers, credentials, or machine-local assumptions. Never claim a check passed unless it was executed. Keep context lean without skipping security, migrations, dependency inspection, or validation. Refresh Graphify after material structural changes.

For UI work, use the existing design system and assess responsive layouts, keyboard/focus behavior, accessibility, loading/empty/error/success states, and light/dark themes where supported. Do not present placeholders or fake metrics as working product behavior.
<!-- END AGENTIC-ENGINEERING-PLATFORM -->
