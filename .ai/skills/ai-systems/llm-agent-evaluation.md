---
name: llm-agent-evaluation
description: "Evaluate LLM agents (TradingAgents, Graphiti retrieval) for schema compliance, grounding, stability, calibration, cost, and latency. Use when prompts, retrieval, or providers change."
---

# LLM Agent Evaluation

## Purpose
LLM agents pass tests too (architecture §21): not just "did they respond".

## Trigger conditions
Prompt changes, provider/model changes, retrieval changes, LLMSignal schema changes.

## Inputs
Prompt/provider/retrieval diff + evaluation dataset (MarketSnapshot + known info as_of T).

## Outputs
Evaluation report across providers/seeds.

## Related agents
`ai-trading-systems` (owner), `verification`.

## Procedure
1. Evaluate: schema compliance, tool usage, grounding, unsupported claims, decision
   stability, confidence calibration, cost, latency, provider variance (§21).
2. Same scenario × different seed/model/provider → direction should not change
   chaotically.
3. Record every evaluation in Langfuse for auditability (§22).
4. Never evaluate against data posterior to the scenario timestamp (INV-3).
