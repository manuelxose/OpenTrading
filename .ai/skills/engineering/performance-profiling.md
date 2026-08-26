---
name: performance-profiling
description: "Profile hot paths and fix bottlenecks. Use when latency, throughput, or memory issues appear in APIs, workers, or ingestion."
---

# Performance Profiling

## Purpose
Measure before optimizing; keep trading-path latency bounded.

## Trigger conditions
Slow endpoints, queue lag, ingestion backlog, LLM pipeline latency.

## Inputs
Profiling data + hot path.

## Outputs
Bottleneck analysis + fix with before/after numbers.

## Related agents
`backend-platform` (owner), `infra-sre`, `ai-trading-systems`.

## Procedure
1. Measure first (cProfile/py-spy, DB explain, broker/queue lag metrics).
2. Identify the bottleneck; fix only that.
3. Watch for N+1 queries, unbounded buffers, blocking ZeroMQ reads.
4. Re-run benchmarks; report before/after.
5. For execution paths: latency budget is part of execution safety.
