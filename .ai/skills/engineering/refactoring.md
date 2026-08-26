---
name: refactoring
description: "Improve code clarity without changing behavior. Use when code works but is hard to read, maintain, or extend."
---

# Refactoring

## Purpose
Simplify while preserving behavior — proven by tests.

## Trigger conditions
Accumulated complexity, duplication, unclear names.

## Inputs
Module under refactor + test coverage.

## Outputs
Refactor diff + green tests.

## Related agents
`backend-platform` (owner), `principal-architect` for boundary refactors.

## Procedure
1. Ensure tests cover current behavior first.
2. Refactor in small steps; run tests each step.
3. Do not mix behavior changes into refactors.
4. Respect domain boundaries (no adapter internals leaking into core).
5. Dead code found → route to dead-code-detection, remove separately.
