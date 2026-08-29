# Point-in-time research context — TradingAgents adapter

Rendered by `adapters/tradingagents/mapper.py` from a canonical `ResearchRequest`
(+ optional `MarketSnapshot`) into the `context_payload` that travels with every
upstream run. `string.Template` placeholders only — no external template engine.

**INV-3 contract:** every value injected below must be valid at `as_of`. The
adapter rejects any `ResearchRequest.context["evidence"]` entry whose
`valid_at > as_of` before this template is rendered.
