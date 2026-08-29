# data/eval/tradingagents — historical evaluation scenarios

Evaluation fixtures for the TradingAgents adapter (architecture §21). Each
`scenarios/*.json` file is one historical scenario: a point-in-time
`MarketSnapshot` + `ResearchRequest` + the expected 5-tier rating and the mock
committee output that should be played back.

Loaded by `adapters/tradingagents/evaluator.py` and exercised by
`tests/unit/tradingagents/test_evaluator.py`. The same fixtures can later be
replayed against the live adapter to compare providers/seeds (§21).

**INV-3 note:** every fixture's `source_timestamp <= as_of`; the evaluator
re-verifies this through the adapter's point-in-time guards.
