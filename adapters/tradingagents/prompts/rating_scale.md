# TradingAgents 5-tier rating → canonical `LLMSignal` mapping

The upstream committee ends in a Portfolio Manager decision carrying exactly one
of five ratings. The adapter maps them to the canonical `SignalDirection` /
`strength` / `confidence` profile below (advisory semantics only — INV-1).

| Upstream rating | `SignalDirection` | `strength` | `confidence` |
|-----------------|-------------------|------------|--------------|
| Buy             | LONG              | 0.90       | 0.80         |
| Overweight      | LONG              | 0.70       | 0.70         |
| Hold            | FLAT              | 0.50       | 0.50         |
| Underweight     | SHORT             | 0.70       | 0.70         |
| Sell            | SHORT             | 0.90       | 0.80         |

These are **advisory**, documented heuristics. They are not calibrated fusion
weights (INV-16) and never produce an `OrderIntent` (INV-1/INV-2). The upstream
Trader's entry price, stop-loss and sizing prose are preserved verbatim in the
Trader committee member's argument as evidence — never as executable values.

Upstream rating render guarantee (v0.3.1): the Portfolio Manager decision always
starts with `**Rating**: <tier>`; the Trader proposal ends with
`FINAL TRANSACTION PROPOSAL: **BUY|HOLD|SELL**`.
