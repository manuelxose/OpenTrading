from adapters.tradingagents.client import _tool_metric_name
from core.observability.metrics import OperationalMetrics
from prometheus_client import CollectorRegistry, generate_latest


def test_operational_metrics_expose_required_low_cardinality_signals() -> None:
    registry = CollectorRegistry()
    metrics = OperationalMetrics(registry=registry)

    metrics.set_service_health("api", True)
    metrics.observe_dependency("postgres", 0.012, True)
    metrics.set_redis_lag("paper:research", 7)
    metrics.set_market_data_age("primary", 3.5)
    metrics.set_mt4_heartbeat_age(1.25)
    metrics.observe_broker_request("submit", 0.08, "ok")
    metrics.observe_execution("filled", 0.11)
    metrics.set_portfolio(pnl=12.5, drawdown=0.02, exposure=1000, risk_utilization=0.4)
    metrics.observe_llm(
        provider="openai",
        model="gpt-5",
        prompt_version="v1",
        duration_seconds=0.4,
        status="ok",
        prompt_tokens=10,
        completion_tokens=5,
        cost_usd=0.01,
    )

    body = generate_latest(registry).decode()
    for metric in (
        "opentrading_service_health",
        "opentrading_dependency_latency_seconds",
        "opentrading_redis_stream_lag",
        "opentrading_market_data_age_seconds",
        "opentrading_mt4_heartbeat_age_seconds",
        "opentrading_broker_request_duration_seconds",
        "opentrading_execution_outcomes_total",
        "opentrading_open_exposure",
        "opentrading_pnl",
        "opentrading_drawdown_ratio",
        "opentrading_risk_utilization_ratio",
        "opentrading_llm_requests_total",
        "opentrading_llm_tokens_total",
        "opentrading_llm_cost_usd_total",
    ):
        assert metric in body


def test_trace_ids_are_not_prometheus_labels() -> None:
    registry = CollectorRegistry()
    OperationalMetrics(registry=registry)

    body = generate_latest(registry).decode()
    assert "trace_id" not in body


def test_upstream_tool_names_map_to_finite_metric_categories() -> None:
    assert _tool_metric_name("get_stock_news") == "news"
    assert _tool_metric_name("attacker-generated-unique-name-123") == "unknown"
