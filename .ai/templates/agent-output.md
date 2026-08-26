# Agent Output Standard

Every implementation agent reports with this structure. Keep it terse; evidence over prose.

```markdown
## Goal
One or two sentences on what was asked and the change class (see cross-review rules).

## Repository evidence
Graphify queries / files inspected / docs read that grounded the change.

## Files affected
List of created/modified files.

## Implementation
What was done and why. Invariant references (INV-n) where relevant.

## Tests
Commands run and results (lint, typecheck, unit, integration, replay, leakage,
property-based, chaos as applicable).

## Risks
Residual risks and anything left unverified, stated honestly.

## Remaining issues
Follow-ups, unblocked by this task.
```

## Anti-patterns

- No "done" claims without the test/check commands and their results.
- No hiding failed checks in prose; classify failures honestly.
- For risk/execution work: explicit statement of which invariants were checked.
