---
name: observability-review
description: "Review observability coverage: Langfuse for AI, Prometheus/Grafana for ops, trace_id end-to-end. Use when instrumentation, metrics, or alerts change."
---

# Observability Review

## Purpose
Every trade must be reconstructible months later (architecture §22, §23, §31).

## Trigger conditions
New services, metrics, alert rules, Langfuse instrumentation.

## Inputs
Component + existing dashboards/alerts.

## Outputs
Coverage gaps list.

## Related agents
`infra-sre` (owner), `ai-trading-systems` (Langfuse), `backend-platform`.

## Procedure
1. Check the §23 dashboard minimum (heartbeat, latency, queue lag, freshness, LLM
   errors/cost/duration, NAV/equity/PnL/drawdown/risk utilization/exposure, spread,
   slippage, fills, rejects).
2. Check §23 alert minimum (heartbeat, stale data, disconnect, unexpected position,
   drawdown/daily loss, rejection spike, LLM/Redis/DB failures).
3. Verify trace_id propagates: MarketSnapshot → agents → risk → order → MT4 →
   execution → trade → postmortem → Obsidian/Langfuse.
4. Secrets must not leak into traces/logs.
