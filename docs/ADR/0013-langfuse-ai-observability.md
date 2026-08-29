# ADR-0013: Langfuse for AI observability

- Status: accepted
- Date: 2026-08-26
- Deciders: principal-architect (+ ai-trading-systems + infra-sre as supporting)

## Context

LLM-heavy workflows (TradingAgents committee, RD-Agent, retrieval) must be auditable:
which prompts, models, tools and traces produced a signal. The decision was frozen in
`docs/architecture.md` §34.15 ("Langfuse será observabilidad de agentes") and detailed
in §22.

## Decision

**Langfuse is the AI observability layer**: prompts, responses, models, costs, latency,
tools, retrieval, and full traces (§22). Every analysis must be reconstructable, e.g.:

```text
TRACE 91901: MarketSnapshot → Graphiti retrieval → Fundamental/Technical/News analysts
→ Bull/Bear researchers → Trader → Portfolio manager → Signal fusion → RiskDecision
→ OrderIntent → Execution
```

A real trade must be auditable months later (§22, §31: `trace_id` spans the entire
pipeline).

## Alternatives considered

- **Custom LLM logging in Postgres** — rejected: §22 freezes Langfuse; reimplementing
  tracing/token/cost tooling is wasted effort.
- **Prometheus/Grafana for AI too** — rejected: operational metrics are a different
  concern (ADR-0014); Langfuse covers model-level traces, evals and prompt lineage.
- **No AI observability** — rejected: §31's end-to-end auditability is a core goal
  ("¿Por qué compramos EURUSD a las 14:23…?" must be answerable).

## Consequences

- Positive: per-trace causality for every LLM decision; cost/latency control; prompt
  versioning.
- Negative: additional infrastructure — provisioned in `infra/compose/langfuse` (§27).
- Follow-ups: wired from Phase 2 (TradingAgents); secrets never logged in Langfuse
  prompts or traces (§29).

## Validation

- Frozen decision §34.15; §22 (trace anatomy); §31 (trace_id everywhere).
- `infra/compose/langfuse` in target layout §27.
- Repo evidence: no observability stack exists yet (PRE-00).
