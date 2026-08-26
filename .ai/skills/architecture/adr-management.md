---
name: adr-management
description: "Create, review, and index Architecture Decision Records. Use when a decision touches frozen decisions, boundaries, event contracts, or data responsibilities."
---

# ADR Management

## Purpose
Record consequential decisions with context and consequences in `docs/ADR/`.

## Trigger conditions
Frozen-decision changes, new service/engine, event envelope changes, store
responsibility changes.

## Inputs
Decision need + `.ai/templates/adr.md`.

## Outputs
`docs/ADR/NNNN-title.md` + index update.

## Related agents
`principal-architect` (owner); `verification`.

## Procedure
1. Confirm an ADR is required (see `.ai/workflows/adr-workflow.md`).
2. Draft: status/context/decision/alternatives/consequences/validation.
3. Principal Architect review → change-class reviewers.
4. Register in `docs/ADR/README.md`.
5. Reject silent violations of frozen decisions.
