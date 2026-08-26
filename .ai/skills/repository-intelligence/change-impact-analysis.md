---
name: change-impact-analysis
description: "Estimate blast radius of a change before editing. Use for cross-cutting edits, shared domain objects, event envelope changes, and risk/execution paths."
---

# Change Impact Analysis

## Purpose
Identify everything a change can break before code is written.

## Trigger conditions
Changes to `core/domain`, events, shared schemas, risk/execution paths, DB schema.

## Inputs
Planned diff or changed symbol.

## Outputs
Affected modules, tests to run, reviewers to include (change class).

## Related agents
`principal-architect`, `verification`, all owners of affected domains.

## Procedure
1. `graphify query` for the symbol and `graphify path` for its neighborhood.
2. Map consumers of changed contracts (events, schemas, APIs).
3. Classify the change class per `.ai/rules/cross-review-rules.md`.
4. List the exact test suites and replay/leakage checks affected.
5. Return the reviewer set — this is the routing input.
