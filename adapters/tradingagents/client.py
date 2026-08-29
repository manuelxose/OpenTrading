"""Live TradingAgents adapter — the ONLY module allowed to import upstream.

Boundary rules (ADR-0004, INV-1, INV-2):

- upstream is imported lazily inside :func:`_load_graph_class` (never at module
  import time), so this package loads fine without TradingAgents installed;
- the installed upstream version is checked against the pin in ``pin.py``;
- every upstream failure is translated into a :class:`TradingAgentsError` —
  no upstream exception ever crosses this boundary;
- timeout and retry budgets are enforced by the adapter;
- the adapter produces only :class:`LLMSignal`. It never creates an
  ``OrderIntent``, never touches MT4, never computes executable position
  sizing. Upstream sizing/stop prose is preserved as evidence text only.
"""

from __future__ import annotations

import os
import tempfile
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from core.observability.metrics import OperationalMetrics, metrics
from core.observability.tracing import LangfuseTracer, tracer
from core.schemas.market import MarketSnapshot
from core.schemas.research import ResearchRequest
from core.schemas.signals import LLMSignal

from adapters.tradingagents import mapper
from adapters.tradingagents.errors import (
    TradingAgentsError,
    TradingAgentsMappingError,
    TradingAgentsTimeoutError,
    TradingAgentsUnavailableError,
    TradingAgentsVersionError,
)
from adapters.tradingagents.pin import UPSTREAM_NAME, UPSTREAM_VERSION
from adapters.tradingagents.schemas import (
    AdapterConfig,
    ModelMetadata,
    TokenUsage,
    UpstreamInput,
    UpstreamRunResult,
)

__all__ = ["LiveTradingAgentsAdapter", "TokenUsageCollector"]

#: Retryable adapter errors consume the retry budget; the rest fail immediately.
_NON_RETRYABLE = (
    TradingAgentsUnavailableError,
    TradingAgentsVersionError,
    TradingAgentsMappingError,
)

#: Largest delay the adapter itself will sleep between attempts.
_DEFAULT_CACHE_DIR = Path(tempfile.gettempdir()) / "opentrading" / "tradingagents"

_TOOL_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("news", "news"),
    ("social", "sentiment"),
    ("sentiment", "sentiment"),
    ("fundamental", "fundamentals"),
    ("financial", "fundamentals"),
    ("macro", "macro"),
    ("price", "market_data"),
    ("stock", "market_data"),
    ("market", "market_data"),
)


def _tool_metric_name(name: str) -> str:
    lowered = name.casefold()
    return next(
        (category for fragment, category in _TOOL_CATEGORIES if fragment in lowered), "unknown"
    )


def _installed_version() -> str | None:
    """Distribution version of the installed upstream, or None if absent."""
    import importlib.metadata as metadata

    try:
        return metadata.version(UPSTREAM_NAME)
    except metadata.PackageNotFoundError:
        return None


def _load_graph_class() -> type:
    """Import the upstream graph class. The single upstream import seam."""
    from tradingagents.graph.trading_graph import (  # type: ignore[import-not-found]
        TradingAgentsGraph,
    )

    return TradingAgentsGraph  # type: ignore[no-any-return]


class TokenUsageCollector:
    """Duck-typed LangChain callback handler accumulating token usage.

    Deliberately imports nothing from LangChain so the adapter has zero
    upstream import-time dependencies. Upstream passes it to the LLM
    constructors via ``callbacks``; if the provider never reports usage, the
    collector simply stays at zero and the result records ``None``.
    """

    def __init__(
        self,
        *,
        telemetry: LangfuseTracer | None = None,
        operational_metrics: OperationalMetrics | None = None,
        trace_id: UUID | None = None,
        provider: str = "unknown",
        model: str = "unknown",
        prompt_version: str = mapper.PROMPT_VERSION,
    ) -> None:
        self._prompt = 0
        self._completion = 0
        self._total = 0
        self._reasoning: int | None = None
        self._calls = 0
        self._telemetry = telemetry or tracer
        self._metrics = operational_metrics or metrics
        self._trace_id = trace_id
        self._tools: dict[object, tuple[str, Any, Any]] = {}
        self._llms: dict[object, tuple[float, Any, Any, str, str]] = {}
        self._provider = provider
        self._model = model
        self._prompt_version = prompt_version

    @property
    def calls(self) -> int:
        return self._calls

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        """Called by LangChain after each LLM generation completes."""
        self._calls += 1
        usage: dict[str, Any] = {}
        llm_output = getattr(response, "llm_output", None) or {}
        if isinstance(llm_output, dict):
            usage.update(llm_output.get("token_usage") or {})
        usage_metadata = getattr(response, "usage_metadata", None)
        if isinstance(usage_metadata, dict):
            usage.update(usage_metadata)

        def _num(key: str) -> int | None:
            value = usage.get(key)
            if isinstance(value, (int, float)) and value >= 0:
                return int(value)
            return None

        for key, slot in (
            ("prompt_tokens", "prompt"),
            ("input_tokens", "prompt"),
            ("completion_tokens", "completion"),
            ("output_tokens", "completion"),
            ("total_tokens", "total"),
            ("reasoning_tokens", "reasoning"),
        ):
            value = _num(key)
            if value is None:
                continue
            if slot == "prompt":
                self._prompt += value
            elif slot == "completion":
                self._completion += value
            elif slot == "total":
                self._total += value
            elif slot == "reasoning":
                self._reasoning = (self._reasoning or 0) + value

        if self._total == 0 and (self._prompt or self._completion):
            self._total = self._prompt + self._completion
        run_id = kwargs.get("run_id")
        if run_id is not None:
            self._finish_llm(run_id, response=response)

    def on_llm_start(
        self, serialized: dict[str, Any], prompts: list[str], *, run_id: object, **kwargs: Any
    ) -> None:
        """Trace the real provider invocation without exporting prompt contents."""
        model = str(
            (kwargs.get("invocation_params") or {}).get("model")
            or serialized.get("name")
            or self._model
        )[:120]
        role = self._callback_role(serialized, kwargs)
        context = None
        observation = None
        if self._trace_id is not None:
            context = self._telemetry.observation(
                trace_id=self._trace_id,
                name=f"tradingagents.{role}",
                as_type="generation",
                model=model,
                metadata={
                    "agent": role,
                    "provider": self._provider,
                    "prompt_version": self._prompt_version,
                    "component": "TradingAgents",
                },
                input={"message_count": len(prompts)},
            )
            observation = context.__enter__()
        self._llms[run_id] = (time.monotonic(), context, observation, role, model)

    def on_chat_model_start(
        self, serialized: dict[str, Any], messages: list[Any], *, run_id: object, **kwargs: Any
    ) -> None:
        self.on_llm_start(serialized, ["" for _ in messages], run_id=run_id, **kwargs)

    def on_llm_error(self, error: BaseException, *, run_id: object, **kwargs: Any) -> None:
        del kwargs
        self._finish_llm(run_id, error=error)

    @staticmethod
    def _callback_role(serialized: dict[str, Any], kwargs: dict[str, Any]) -> str:
        metadata = kwargs.get("metadata") or {}
        haystack = " ".join(
            str(value)
            for value in (
                serialized.get("name"),
                serialized.get("id"),
                metadata.get("langgraph_node"),
                metadata.get("agent"),
                kwargs.get("tags"),
            )
            if value is not None
        ).casefold()
        if "portfolio" in haystack or "risk manager" in haystack:
            return "portfolio_manager"
        if "trader" in haystack:
            return "trader"
        if "research" in haystack or "bull" in haystack or "bear" in haystack:
            return "researcher"
        if "analyst" in haystack:
            return "analyst"
        return "committee"

    def _finish_llm(
        self, run_id: object, *, response: Any | None = None, error: BaseException | None = None
    ) -> None:
        item = self._llms.pop(run_id, None)
        if item is None:
            return
        began, context, observation, role, model = item
        duration = time.monotonic() - began
        usage = self._usage_from_response(response) if response is not None else {}
        status = "error" if error is not None else "ok"
        self._metrics.observe_llm(
            provider=self._provider,
            model=model,
            prompt_version=self._prompt_version,
            duration_seconds=duration,
            status=status,
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            cost_usd=float(usage.get("cost_usd", 0)),
        )
        if observation is not None:
            observation.update(
                output={"response_type": type(response).__name__} if response is not None else None,
                usage_details={
                    "input": usage.get("prompt_tokens", 0),
                    "output": usage.get("completion_tokens", 0),
                    "total": usage.get("total_tokens", 0),
                },
                cost_details={"total": float(usage.get("cost_usd", 0))},
                metadata={"agent": role, "status": status},
            )
            if error is None:
                context.__exit__(None, None, None)
            else:
                context.__exit__(type(error), error, error.__traceback__)

    @staticmethod
    def _usage_from_response(response: Any) -> dict[str, int | float]:
        output = getattr(response, "llm_output", None) or {}
        usage = output.get("token_usage", {}) if isinstance(output, dict) else {}
        return {
            "prompt_tokens": int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0),
            "completion_tokens": int(
                usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0
            ),
            "total_tokens": int(usage.get("total_tokens", 0) or 0),
            "cost_usd": float(output.get("cost_usd", 0) or 0) if isinstance(output, dict) else 0,
        }

    def to_token_usage(self) -> TokenUsage | None:
        if self._calls == 0:
            return None
        return TokenUsage(
            calls=self._calls,
            prompt_tokens=self._prompt,
            completion_tokens=self._completion,
            total_tokens=self._total,
            reasoning_tokens=self._reasoning,
        )

    def on_tool_start(
        self, serialized: dict[str, Any], input_str: str, *, run_id: object, **kwargs: Any
    ) -> None:
        """LangChain callback: start a Langfuse tool observation."""
        del kwargs
        name = str(serialized.get("name") or "unknown")[:80]
        if self._trace_id is None:
            self._tools[run_id] = (name, None, None)
            return
        context = self._telemetry.observation(
            trace_id=self._trace_id,
            name=f"tool.{name}",
            as_type="tool",
            metadata={"tool": name, "component": "TradingAgents"},
            input={"input_length": len(input_str)},
        )
        observation = context.__enter__()
        self._tools[run_id] = (name, context, observation)

    def on_tool_end(self, output: Any, *, run_id: object, **kwargs: Any) -> None:
        del kwargs
        name, context, observation = self._tools.pop(run_id, ("unknown", None, None))
        self._metrics.tool_calls.labels(tool=_tool_metric_name(name), status="ok").inc()
        if observation is not None:
            observation.update(output={"output_type": type(output).__name__})
            context.__exit__(None, None, None)

    def on_tool_error(self, error: BaseException, *, run_id: object, **kwargs: Any) -> None:
        del kwargs
        name, context, observation = self._tools.pop(run_id, ("unknown", None, None))
        self._metrics.tool_calls.labels(tool=_tool_metric_name(name), status="error").inc()
        if observation is not None:
            observation.update(metadata={"status": "error", "error_type": type(error).__name__})
            context.__exit__(type(error), error, error.__traceback__)


class LiveTradingAgentsAdapter:
    """Strict adapter boundary around ``TradingAgentsGraph.propagate``.

    Lifecycle per ``run()``: translate the request → (lazy) build the upstream
    graph → execute with timeout inside a worker thread → normalize state →
    translate to ``LLMSignal``. Attempts beyond the retry budget, timeouts and
    upstream crashes all surface as :class:`TradingAgentsError`.
    """

    name = "tradingagents-live"

    def __init__(
        self,
        config: AdapterConfig,
        *,
        clock_now: Callable[[], datetime] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        telemetry: LangfuseTracer | None = None,
        operational_metrics: OperationalMetrics | None = None,
    ) -> None:
        self._config = config
        self._clock_now = clock_now or mapper.now_utc
        self._sleep = sleep
        self._telemetry = telemetry or tracer
        self._metrics = operational_metrics or metrics
        #: Result of the most recent successful run (diagnostics/evaluation).
        self.last_result: UpstreamRunResult | None = None

    def run(
        self,
        request: ResearchRequest,
        snapshot: MarketSnapshot | None = None,
        *,
        trace_id: UUID | None = None,
        now: datetime | None = None,
    ) -> LLMSignal:
        """Execute the upstream committee for ``request`` and return a signal.

        Fails safely: never raises anything but :class:`TradingAgentsError`.
        """
        started = now or self._clock_now()
        upstream_input = mapper.request_to_upstream_input(request, snapshot)

        attempt = 1
        while True:
            try:
                return self._execute(
                    request, snapshot, upstream_input, trace_id=trace_id, now=started
                )
            except TradingAgentsError as exc:
                if attempt >= self._config.retry_max_attempts or isinstance(exc, _NON_RETRYABLE):
                    raise
                delay = min(
                    self._config.retry_base_delay_seconds
                    * (self._config.retry_backoff_factor ** (attempt - 1)),
                    self._config.retry_delay_cap_seconds,
                )
                if delay > 0:
                    self._sleep(delay)
                attempt += 1

    # ── internals ────────────────────────────────────────────────────────────

    def _execute(
        self,
        request: ResearchRequest,
        snapshot: MarketSnapshot | None,
        upstream_input: UpstreamInput,
        *,
        trace_id: UUID | None,
        now: datetime,
    ) -> LLMSignal:
        graph_class = _load_graph_class_safely()
        installed = _installed_version_safely()
        if installed is not None and installed != UPSTREAM_VERSION:
            raise TradingAgentsVersionError(
                f"upstream version {installed!r} violates the pin "
                f"{UPSTREAM_VERSION!r} (commit of pin.py/external-lock.yaml)"
            )
        meta = ModelMetadata(
            provider=self._config.llm_provider,
            deep_think_llm=self._config.deep_think_llm,
            quick_think_llm=self._config.quick_think_llm,
            upstream_version=UPSTREAM_VERSION,
            upstream_version_detected=installed,
            prompt_version=mapper.PROMPT_VERSION,
        )

        trace_uuid = trace_id or request.request_id
        collector = TokenUsageCollector(
            telemetry=self._telemetry,
            operational_metrics=self._metrics,
            trace_id=trace_uuid,
            provider=self._config.llm_provider,
            model=self._config.deep_think_llm,
            prompt_version=mapper.PROMPT_VERSION,
        )
        graph = self._build_graph(graph_class, callbacks=[collector])

        began = time.monotonic()
        with self._telemetry.observation(
            trace_id=trace_uuid,
            name="tradingagents.committee",
            as_type="generation",
            model=self._config.deep_think_llm,
            metadata={
                "provider": self._config.llm_provider,
                "prompt_version": mapper.PROMPT_VERSION,
                "component": "TradingAgents",
                "instrument_id": upstream_input.ticker,
            },
            input={"instrument_id": upstream_input.ticker, "as_of": upstream_input.trade_date},
        ) as generation:
            state, upstream_rating = self._propagate(
                graph, upstream_input.ticker, upstream_input.trade_date, upstream_input.asset_type
            )
            latency_ms = int((time.monotonic() - began) * 1000)
            usage = collector.to_token_usage()
            generation.update(
                output={"rating": str(upstream_rating or "")},
                usage_details=(
                    {
                        "input": usage.prompt_tokens,
                        "output": usage.completion_tokens,
                        "total": usage.total_tokens,
                    }
                    if usage is not None
                    else None
                ),
                metadata={"status": "ok", "latency_ms": latency_ms},
            )

        rating = mapper.parse_rating(str(state.get("final_trade_decision") or ""))
        # Cross-check the upstream SignalProcessor rating against ours.
        if upstream_rating:
            upstream_tier = mapper.parse_rating(str(upstream_rating))
            if upstream_tier != rating:
                raise TradingAgentsMappingError(
                    f"upstream rating {upstream_tier.value!r} disagrees with parsed "
                    f"decision rating {rating.value!r}"
                )

        result = mapper.state_to_result(
            state,
            ticker=upstream_input.ticker,
            as_of=upstream_input.as_of,
            rating=rating,
            latency_ms=latency_ms,
            model_metadata=meta,
            token_usage=usage,
            cost_usd=None,  # upstream exposes no cost; recorded only when available
            trace_id=trace_id,
        )
        self.last_result = result
        return mapper.result_to_signal(
            result, request=request, snapshot=snapshot, trace_id=trace_id, produced_at=now
        )

    def _build_graph(self, graph_class: type, *, callbacks: list[Any]) -> Any:
        """Instantiate the upstream graph with a sanitized config dict."""
        cfg = self._config
        upstream_config: dict[str, Any] = {
            "llm_provider": cfg.llm_provider,
            "deep_think_llm": cfg.deep_think_llm,
            "quick_think_llm": cfg.quick_think_llm,
            "max_debate_rounds": cfg.max_debate_rounds,
            "max_risk_discuss_rounds": cfg.max_risk_discuss_rounds,
            "llm_max_retries": cfg.llm_max_retries,
            "checkpoint_enabled": cfg.checkpoint_enabled,
        }
        if cfg.temperature is not None:
            upstream_config["temperature"] = cfg.temperature
        if cfg.backend_url:
            upstream_config["backend_url"] = cfg.backend_url

        cache_dir = cfg.data_cache_dir or _DEFAULT_CACHE_DIR / "cache"
        results_dir = cfg.results_dir or _DEFAULT_CACHE_DIR / "results"
        os.makedirs(cache_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)
        upstream_config["data_cache_dir"] = str(cache_dir)
        upstream_config["results_dir"] = str(results_dir)
        upstream_config.update(cfg.upstream_extra)

        try:
            return graph_class(
                selected_analysts=cfg.selected_analysts,
                debug=False,
                config=upstream_config,
                callbacks=callbacks,
            )
        except TradingAgentsError:
            raise
        except Exception as exc:
            raise TradingAgentsUnavailableError(
                f"could not instantiate upstream graph: {exc}"
            ) from exc

    def _propagate(
        self, graph: Any, ticker: str, trade_date: str, asset_type: str
    ) -> tuple[dict[str, Any], str]:
        """Run propagate in a worker thread under the adapter timeout budget.

        Note: a timed-out worker thread cannot be killed; it is abandoned and
        the executor is shut down without waiting, so the budget violation is
        reported promptly (fail-safe, documented).
        """
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(graph.propagate, ticker, trade_date, asset_type)
            try:
                return future.result(timeout=self._config.timeout_seconds)  # type: ignore[no-any-return]
            except FuturesTimeout as exc:
                raise TradingAgentsTimeoutError(
                    f"upstream run for {ticker}@{trade_date} exceeded "
                    f"{self._config.timeout_seconds}s timeout budget"
                ) from exc
            except Exception as exc:
                raise TradingAgentsError(f"upstream propagate failed: {exc}") from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)


def _load_graph_class_safely() -> type:
    try:
        return _load_graph_class()
    except ImportError as exc:
        raise TradingAgentsUnavailableError(
            "TradingAgents is not installed. Install the pinned commit: "
            'uv pip install "tradingagents @ git+https://github.com/TauricResearch/'
            'TradingAgents@a33fd4c0f134485a43553a2c23a63cb14adbd88f"'
        ) from exc
    except Exception as exc:
        raise TradingAgentsUnavailableError(f"upstream import failed: {exc}") from exc


def _installed_version_safely() -> str | None:
    try:
        return _installed_version()
    except Exception as exc:
        raise TradingAgentsError(f"could not resolve upstream version: {exc}") from exc
