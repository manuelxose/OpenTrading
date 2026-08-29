from types import SimpleNamespace
from uuid import uuid4

from adapters.tradingagents.client import TokenUsageCollector
from core.observability.metrics import OperationalMetrics
from core.observability.tracing import LangfuseTracer, NullObservation, deterministic_trace_id
from prometheus_client import CollectorRegistry, generate_latest


class _Observation:
    def __init__(self) -> None:
        self.updates: list[dict[str, object]] = []

    def __enter__(self) -> "_Observation":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def update(self, **kwargs: object) -> None:
        self.updates.append(kwargs)


class _Client:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.observation = _Observation()

    def start_as_current_observation(self, **kwargs: object) -> _Observation:
        self.calls.append(kwargs)
        return self.observation


class _BrokenContext:
    def __init__(self, failure: str) -> None:
        self.failure = failure

    def __enter__(self) -> _Observation:
        if self.failure == "start":
            raise RuntimeError("start failed")
        observation = _Observation()
        if self.failure == "update":

            def broken_update(**kwargs: object) -> None:
                del kwargs
                raise RuntimeError("update failed")

            observation.update = broken_update  # type: ignore[method-assign]
        return observation

    def __exit__(self, *args: object) -> None:
        if self.failure == "exit":
            raise RuntimeError("exit failed")


class _BrokenClient:
    def __init__(self, failure: str) -> None:
        self.failure = failure

    def start_as_current_observation(self, **kwargs: object) -> _BrokenContext:
        del kwargs
        return _BrokenContext(self.failure)


def test_langfuse_trace_uses_domain_trace_id_and_sanitized_metadata() -> None:
    trace_id = uuid4()
    client = _Client()
    tracer = LangfuseTracer(client=client, enabled=True)

    with tracer.observation(
        trace_id=trace_id,
        name="research",
        as_type="agent",
        metadata={"stage": "research", "password": "must-not-leak"},
    ) as observation:
        observation.update(output={"status": "ok"})

    call = client.calls[0]
    assert call["trace_context"] == {"trace_id": deterministic_trace_id(trace_id)}
    assert call["metadata"] == {"stage": "research", "domain_trace_id": str(trace_id)}


def test_disabled_tracer_is_noop() -> None:
    tracer = LangfuseTracer(enabled=False)
    with tracer.observation(trace_id=uuid4(), name="disabled") as observation:
        assert isinstance(observation, NullObservation)


def test_langfuse_failures_never_escape_into_domain_code() -> None:
    for failure in ("start", "update", "exit"):
        tracer = LangfuseTracer(client=_BrokenClient(failure), enabled=True)
        with tracer.observation(trace_id=uuid4(), name="safe") as observation:
            observation.update(output={"ok": True})


def test_tradingagents_callback_traces_real_role_generation_and_usage() -> None:
    client = _Client()
    operational_metrics = OperationalMetrics(registry=CollectorRegistry())
    collector = TokenUsageCollector(
        telemetry=LangfuseTracer(client=client, enabled=True),
        operational_metrics=operational_metrics,
        trace_id=uuid4(),
        provider="openai",
        model="fallback-model",
        prompt_version="prompt-v2",
    )

    collector.on_llm_start(
        {"name": "ChatOpenAI"},
        ["redacted prompt"],
        run_id="run-1",
        metadata={"langgraph_node": "trader"},
        invocation_params={"model": "gpt-5"},
    )
    collector.on_llm_end(
        SimpleNamespace(
            llm_output={
                "token_usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16},
                "cost_usd": 0.02,
            }
        ),
        run_id="run-1",
    )

    assert client.calls[0]["name"] == "tradingagents.trader"
    assert client.calls[0]["model"] == "gpt-5"
    assert client.calls[0]["input"] == {"message_count": 1}
    assert "redacted prompt" not in str(client.calls)
    body = generate_latest(operational_metrics.registry).decode()
    assert 'provider="openai"' in body
    assert 'model="gpt-5"' in body
    assert 'prompt_version="prompt-v2"' in body
    assert (
        'opentrading_llm_requests_total{model="gpt-5",prompt_version="prompt-v2",'
        'provider="openai",status="ok"} 1.0'
    ) in body
    assert (
        'opentrading_llm_tokens_total{model="gpt-5",prompt_version="prompt-v2",'
        'provider="openai",type="prompt"} 12.0'
    ) in body
    assert (
        'opentrading_llm_cost_usd_total{model="gpt-5",prompt_version="prompt-v2",'
        'provider="openai"} 0.02'
    ) in body
