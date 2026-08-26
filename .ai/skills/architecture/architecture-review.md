---
name: architecture-review
description: "Check a change against the architecture invariants and system boundaries. Use when reviewing or designing cross-cutting, domain, event, or service changes."
---

# Architecture Review

## Purpose
Keep the platform coherent with `docs/architecture.md` and its invariants.

## Trigger conditions
Architecture-wide or boundary changes, pre-merge review of domain work.

## Inputs
Diff/design + `.ai/rules/architecture-invariants.md`.

## Outputs
Invariant-by-invariant verdict with violations.

## Related agents
`principal-architect` (owner); `verification` (enforcer).

## Procedure
1. Identify which invariants (INV-1..INV-16) the change touches.
2. Verify each is preserved; cite the evidence.
3. Check boundary direction: `core` never imports adapters; engines stay independent.
4. Check for duplicated implementations (INV-2) and store misuse (INV-10).
5. If a frozen decision changes → require ADR before approval.
