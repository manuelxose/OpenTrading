# adapters/tradingagents — TradingAgents behind a strict boundary (ADR-0004)

Qualitative, multi-agent LLM research committee (TauricResearch/TradingAgents),
integrated **read-only**:

```text
MarketSnapshot ─┐
                ├─► ResearchRequest ─► TradingAgents ─► LLMSignal
ResearchRequest ┘
```

## Boundary rules

- `client.py` is the ONLY module that imports upstream, and it does so lazily
  (never at package import time). Upstream exceptions never escape the adapter.
- The rest of the application never imports `tradingagents` classes — enforced
  by `tests/unit/tradingagents/test_boundary.py` and the core import guard in
  `tests/unit/domain/test_import_guard.py`.
- The adapter never creates an `OrderIntent`, never calls MT4, never computes
  executable position sizing (INV-1/INV-2). Upstream Trader entry/stop/sizing
  prose is preserved verbatim as **evidence text** in the Trader committee
  member's argument — never as executable values.

## Upstream pin (INV-14)

| Field   | Value                                            |
|---------|--------------------------------------------------|
| repo    | https://github.com/TauricResearch/TradingAgents  |
| tag     | `v0.3.1`                                         |
| version | `0.3.1`                                          |
| commit  | `a33fd4c0f134485a43553a2c23a63cb14adbd88f`       |
| license | Apache-2.0                                       |

Recorded in `pin.py` and `external-lock.yaml`. Install exactly:

```bash
uv pip install "tradingagents @ git+https://github.com/TauricResearch/TradingAgents@a33fd4c0f134485a43553a2c23a63cb14adbd88f"
```

The live adapter verifies the installed distribution version against the pin at
run time and fails safely (`TradingAgentsVersionError`) on a mismatch. If
TradingAgents is not installed at all, the package still imports and the live
adapter raises `TradingAgentsUnavailableError` — the rest of the domain works
(the mock adapter and the contract tests prove it).

## Usage

```python
from adapters.tradingagents import LiveTradingAgentsAdapter, AdapterConfig

adapter = LiveTradingAgentsAdapter(
    AdapterConfig(
        llm_provider="openai",
        deep_think_llm="gpt-5.5",
        quick_think_llm="gpt-5.4-mini",
        timeout_seconds=600,
        retry_max_attempts=2,
    )
)
signal = adapter.run(request, snapshot, trace_id=trace_id)
```

`signal` is a canonical `LLMSignal`: direction/strength/confidence from the
documented 5-tier profile (`prompts/rating_scale.md`), committee evidence
preserving analyst / researcher / trader / portfolio-manager output,
model/provider/version metadata, token usage when reported, `trace_id`, and the
explicit `as_of` anchor.

## Point-in-time contract (INV-3)

`as_of` is explicit and required (snapshot, or `request.context["as_of"]`).
The adapter refuses any injected `context["evidence"]` entry whose `valid_at`
is posterior to `as_of`, and re-checks the snapshot invariant. The rendered
point-in-time context block (`prompts/context.md`) travels with the run for
auditability; upstream itself is invoked with `propagate(ticker, trade_date)`
so its vendor data is pinned to the same trade date.

## Tests

`tests/unit/tradingagents/` — mapper, client (fail-safe/timeout/retry/pin),
mock adapter, boundary (TradingAgents can disappear entirely), evaluator, and
the end-to-end `MarketSnapshot → ResearchRequest → TradingAgents → LLMSignal`
contract with no execution capability.
