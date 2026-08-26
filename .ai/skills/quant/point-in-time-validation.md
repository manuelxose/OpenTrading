---
name: point-in-time-validation
description: "Verify no look-ahead: every query in simulated contexts carries as_of and nothing posterior to T is visible. Use when touching data, snapshots, memory retrieval, or backtest inputs."
---

# Point-in-Time Validation

## Purpose
Enforce the strictest rule of the project (architecture §12, INV-3): a backtest at time T
may not see anything after T — prices, news, macro revisions, memory, embeddings,
postmortems, knowledge graph.

## Trigger conditions
Ingest, snapshot construction, Graphiti retrieval, feature computation, backtest inputs.

## Inputs
Code under review + simulation clock semantics.

## Outputs
Violation list and required leakage tests.

## Related agents
`market-data` and `quant-research` (owners), `ai-trading-systems` (memory queries).

## Procedure
1. Find every data/memory access in simulated paths; confirm an `as_of` parameter.
2. Confirm `source_timestamp <= simulation_timestamp` is enforced.
3. Confirm no dataset/memory preloading before backtest start.
4. Add/run leakage tests that FAIL on future access.
5. Check Graphiti queries use `memory.query(valid_at=simulation_clock.now())` (§12).
