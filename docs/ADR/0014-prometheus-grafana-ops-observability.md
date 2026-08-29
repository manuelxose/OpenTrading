# ADR-0014: Prometheus + Grafana for operational observability

- Status: accepted
- Date: 2026-08-26
- Deciders: principal-architect (+ infra-sre + risk for alert definitions)

## Context

The platform needs operational and trading observability distinct from LLM observability.
The decision was frozen in `docs/architecture.md` §34.16 ("Prometheus/Grafana serán
observabilidad operacional") and detailed in §23.

## Decision

**Prometheus + Grafana measure the system and the trading operation** (§23).

- Minimum dashboard: MT4 heartbeat, execution latency, broker latency, queue lag, data
  freshness, LLM errors/cost, agent duration, NAV, equity, PnL, drawdown, risk
  utilization, open exposure, spread, slippage, fills, rejects.
- Alerts: missing heartbeat, stale market data, broker disconnected, unexpected position,
  drawdown threshold, daily-loss threshold, order-rejection spike, LLM provider failure,
  Redis failure, DB failure.

AI-specific observability stays with Langfuse (ADR-0013); the split is part of §23's
division of labor.

## Alternatives considered

- **One tool for everything (Langfuse-only or Grafana-only)** — rejected: §22–§23 define
  the split; trace-level AI introspection and ops metrics are different data models.
- **Commercial APM (Datadog/New Relic)** — rejected: frozen decision §34.16 plus
  self-hosted posture (MinIO, FalkorDB, etc.).
- **Logs-only monitoring** — rejected: real-time gauges (NAV, exposure, heartbeat) and
  alert rules need a metrics store.

## Consequences

- Positive: heartbeat/drawdown/broker-state visibility is a safety control — it feeds
  the Risk Engine inputs (§7) and kill-switch awareness (§10).
- Negative: another two services in `infra/compose` (§27) — accepted operational cost.
- Follow-ups: provisioned in Phase 1+; alert thresholds reviewed by `risk`; operational
  dashboards land before Phase 8 (LIVE_GATED).

## Validation

- Frozen decision §34.16; §23 (dashboard minimum + alert list); §31 (trace join).
- `infra/compose/prometheus` + `grafana` in target layout §27.
- Repo evidence: no monitoring exists yet (PRE-00).
