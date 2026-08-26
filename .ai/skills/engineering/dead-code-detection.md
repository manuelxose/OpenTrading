---
name: dead-code-detection
description: "Find and remove unreachable or unused code. Use during reviews and before major refactors."
---

# Dead Code Detection

## Purpose
Remove paths that are never exercised — especially near-miss implementations that can
diverge (INV-2).

## Trigger conditions
Review time, refactors, strategy retirement, mode changes.

## Inputs
Module/tree.

## Outputs
Dead-code list with removal plan.

## Related agents
`verification` (owner), `backend-platform`.

## Procedure
1. Find unused symbols (static tools + grep + graphify usages).
2. Check for hidden divergent implementations (backtest vs live copies).
3. Remove in a separate change from feature work.
4. Verify tests still pass; no production path referenced dead code.
