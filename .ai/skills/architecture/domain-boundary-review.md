---
name: domain-boundary-review
description: "Check that canonical domain objects stay independent of external projects (TradingAgents, Nautilus, Graphiti, MT4). Use when adapters or core domain objects change."
---

# Domain Boundary Review

## Purpose
Keep the core replaceable: no external project type may leak into `core/domain`.

## Trigger conditions
Changes to `core/domain`, adapter interfaces, canonical objects (§15).

## Inputs
Diff of domain or adapter code.

## Outputs
Boundary violations list.

## Related agents
`principal-architect` (owner), `backend-platform`.

## Procedure
1. Confirm canonical objects (`OrderIntent`, `RiskDecision`, etc.) use only core types.
2. Confirm adapters map external types → core types and never the reverse.
3. Confirm no import of TradingAgents/Nautilus/Graphiti/MT4 internals outside their
   adapter.
4. Confirm the domain can be tested without external services.
