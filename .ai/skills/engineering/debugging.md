---
name: debugging
description: "Systematic root-cause debugging. Use when tests fail, builds break, or behavior doesn't match expectations."
---

# Debugging

## Purpose
Find root cause, not symptoms; no guessing.

## Trigger conditions
Failing tests/builds, unexpected runtime behavior.

## Inputs
Failure output, logs, trace_id where available.

## Outputs
Root cause + fix + regression test.

## Related agents
All.

## Procedure
1. Reproduce with minimal input.
2. Follow trace_id across services (§31) when a trading path is involved.
3. Inspect state transitions (order lifecycle) rather than guessing.
4. Fix root cause; add regression test.
5. Classify honestly: logic bug vs data issue vs infra.
