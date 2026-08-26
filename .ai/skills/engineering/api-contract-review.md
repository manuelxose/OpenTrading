---
name: api-contract-review
description: "Review API and protocol contracts (FastAPI, ZeroMQ MT4 protocol, adapter interfaces, data schemas). Use when any interface changes."
---

# API Contract Review

## Purpose
Contracts change deliberately, versioned, and without breaking consumers silently.

## Trigger conditions
Endpoint changes, protocol message changes, adapter interface changes, schema changes.

## Inputs
Diff of the contract.

## Outputs
Compatibility verdict + migration notes.

## Related agents
`backend-platform`, `execution-mt4`, `ai-trading-systems`, `market-data` (as owners).

## Procedure
1. Identify all consumers (graphify usages + event consumers).
2. Version the contract; define compatibility for additive vs breaking changes.
3. For MT4 protocol: schema_version + checksum per message (§8).
4. For data contracts: schema version + point-in-time semantics.
5. Update tests on both sides of the contract.
