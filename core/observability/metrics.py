"""Bounded-cardinality Prometheus metrics for the trading runtime."""

from __future__ import annotations

from typing import Any

from prometheus_client import REGISTRY, CollectorRegistry, Counter, Gauge, Histogram

_LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 15, 60)


class OperationalMetrics:
    """Own all application metrics so tests can use an isolated registry."""

    def __init__(self, *, registry: CollectorRegistry = REGISTRY) -> None:
        self.registry = registry
        common: dict[str, Any] = {"registry": registry, "namespace": "opentrading"}
        self.service_health = Gauge(
            "service_health", "Service health (1 healthy, 0 unhealthy)", ["service"], **common
        )
        self.dependency_latency = Histogram(
            "dependency_latency_seconds",
            "Dependency probe latency",
            ["dependency", "status"],
            buckets=_LATENCY_BUCKETS,
            **common,
        )
        self.redis_lag = Gauge(
            "redis_stream_lag", "Redis Stream consumer lag", ["consumer_group"], **common
        )
        self.market_data_age = Gauge(
            "market_data_age_seconds", "Age of latest market data", ["source"], **common
        )
        self.market_data_last_update = Gauge(
            "market_data_last_update_timestamp_seconds",
            "Timestamp of latest market data",
            ["source"],
            **common,
        )
        self.mt4_heartbeat_age = Gauge(
            "mt4_heartbeat_age_seconds", "Age of latest MT4 heartbeat", **common
        )
        self.mt4_last_heartbeat = Gauge(
            "mt4_last_heartbeat_timestamp_seconds", "Timestamp of latest MT4 heartbeat", **common
        )
        self.broker_duration = Histogram(
            "broker_request_duration_seconds",
            "Broker request latency",
            ["operation", "status"],
            buckets=_LATENCY_BUCKETS,
            **common,
        )
        self.execution_duration = Histogram(
            "execution_latency_seconds",
            "Order execution latency",
            ["outcome"],
            buckets=_LATENCY_BUCKETS,
            **common,
        )
        self.execution_outcomes = Counter(
            "execution_outcomes", "Execution fill/reject outcomes", ["outcome"], **common
        )
        self.open_exposure = Gauge("open_exposure", "Open notional exposure", **common)
        self.pnl = Gauge("pnl", "Current portfolio profit and loss", **common)
        self.drawdown = Gauge("drawdown_ratio", "Current portfolio drawdown ratio", **common)
        self.risk_utilization = Gauge(
            "risk_utilization_ratio", "Current deterministic risk budget utilization", **common
        )
        self.daily_loss = Gauge("daily_loss", "Current positive daily loss amount", **common)
        self.daily_loss_limit = Gauge(
            "daily_loss_limit", "Configured deterministic daily loss limit", **common
        )
        self.drawdown_limit = Gauge(
            "drawdown_limit_ratio", "Configured deterministic drawdown limit", **common
        )
        self.llm_requests = Counter(
            "llm_requests",
            "LLM request outcomes",
            ["provider", "model", "prompt_version", "status"],
            **common,
        )
        self.llm_duration = Histogram(
            "llm_request_duration_seconds",
            "LLM request latency",
            ["provider", "model", "prompt_version", "status"],
            buckets=_LATENCY_BUCKETS,
            **common,
        )
        self.llm_tokens = Counter(
            "llm_tokens",
            "LLM token usage",
            ["provider", "model", "prompt_version", "type"],
            **common,
        )
        self.llm_cost = Counter(
            "llm_cost_usd", "LLM cost in USD", ["provider", "model", "prompt_version"], **common
        )
        self.tool_calls = Counter(
            "agent_tool_calls", "Agent tool call outcomes", ["tool", "status"], **common
        )
        self.retrieval_duration = Histogram(
            "retrieval_duration_seconds",
            "Retrieval latency",
            ["backend", "status"],
            buckets=_LATENCY_BUCKETS,
            **common,
        )
        self.retrieval_hits = Histogram(
            "retrieval_hits",
            "Retrieval result count",
            ["backend"],
            buckets=(0, 1, 2, 5, 10, 20, 50, 100),
            **common,
        )
        self.pipeline_stage_duration = Histogram(
            "pipeline_stage_duration_seconds",
            "Pipeline stage latency",
            ["stage", "status"],
            buckets=_LATENCY_BUCKETS,
            **common,
        )
        self.pipeline_errors = Counter(
            "pipeline_stage_errors", "Pipeline stage failures", ["stage", "error_type"], **common
        )
        self.unexpected_broker_positions = Gauge(
            "unexpected_broker_positions", "Material broker position discrepancies", **common
        )

    def set_service_health(self, service: str, healthy: bool) -> None:
        self.service_health.labels(service=service).set(1 if healthy else 0)

    def observe_dependency(self, dependency: str, duration: float, healthy: bool) -> None:
        self.dependency_latency.labels(
            dependency=dependency, status="ok" if healthy else "error"
        ).observe(duration)

    def set_redis_lag(self, consumer_group: str, lag: int) -> None:
        self.redis_lag.labels(consumer_group=consumer_group).set(lag)

    def set_market_data_age(self, source: str, age_seconds: float) -> None:
        self.market_data_age.labels(source=source).set(max(0, age_seconds))

    def set_market_data_timestamp(self, source: str, timestamp: float) -> None:
        self.market_data_last_update.labels(source=source).set(timestamp)

    def set_mt4_heartbeat_age(self, age_seconds: float) -> None:
        self.mt4_heartbeat_age.set(max(0, age_seconds))

    def set_mt4_heartbeat_timestamp(self, timestamp: float) -> None:
        self.mt4_last_heartbeat.set(timestamp)

    def observe_broker_request(self, operation: str, duration: float, status: str) -> None:
        self.broker_duration.labels(operation=operation, status=status).observe(duration)

    def observe_execution(self, outcome: str, duration: float) -> None:
        self.execution_outcomes.labels(outcome=outcome).inc()
        self.execution_duration.labels(outcome=outcome).observe(duration)

    def set_portfolio(
        self,
        *,
        pnl: float,
        drawdown: float,
        exposure: float,
        risk_utilization: float,
        daily_loss: float = 0.0,
        daily_loss_limit: float = 0.0,
        drawdown_limit: float = 0.0,
    ) -> None:
        self.pnl.set(pnl)
        self.drawdown.set(drawdown)
        self.open_exposure.set(exposure)
        self.risk_utilization.set(risk_utilization)
        self.daily_loss.set(max(0, daily_loss))
        self.daily_loss_limit.set(max(0, daily_loss_limit))
        self.drawdown_limit.set(max(0, drawdown_limit))

    def observe_llm(
        self,
        *,
        provider: str,
        model: str,
        prompt_version: str,
        duration_seconds: float,
        status: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        labels = {"provider": provider, "model": model, "prompt_version": prompt_version}
        self.llm_requests.labels(**labels, status=status).inc()
        self.llm_duration.labels(**labels, status=status).observe(duration_seconds)
        self.llm_tokens.labels(**labels, type="prompt").inc(prompt_tokens)
        self.llm_tokens.labels(**labels, type="completion").inc(completion_tokens)
        self.llm_cost.labels(**labels).inc(max(0, cost_usd))


metrics = OperationalMetrics()
