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
