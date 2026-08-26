---
name: incident-analysis
description: "Analyze incidents post-mortem: evidence first, safe mitigation, regression protection. Use during and after failures."
---

# Incident Analysis

## Purpose
Recover safely and learn; every incident ends in a postmortem feeding Graphiti memory.

## Trigger conditions
Broker disconnect, reconciliation divergence, SAFE_MODE entries, data/DB failures,
LLM provider failures.

## Inputs
Alerts, logs, traces, state snapshots.

## Outputs
Timeline, root cause, mitigation, postmortem.

## Related agents
`infra-sre` (owner), relevant domain agents, `security` if relevant.

## Procedure
1. Evidence before edits; preserve state and logs.
2. Safe mitigation first (kill switch / SAFE_MODE semantics per §7/§10).
3. Root cause with trace_id reconstruction (§31).
4. Regression protection: test or alert for recurrence.
5. Write postmortem; feed `PostTradeReview`/Graphiti episode if trading-related.
