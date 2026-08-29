# tests/unit/signal_fusion — Signal Fusion Engine tests

Covers INV-16 and ADR-0019:

- `test_fusion_engine.py` — weighted math, flat threshold, errors.
- `test_fusion_conflicts.py` — disagreement policies (NEUTRALIZE /
  TRUST_HIGHER_CONFIDENCE / REQUIRE_CONSENSUS).
- `test_fusion_missing.py` — missing LLM / QuantSignal, REQUIRE_QUANT, empty.
- `test_fusion_extreme.py` — confidence 0/1 boundaries and invalid values.
- `test_fusion_deterministic.py` — identical inputs → identical signals.
- `test_calibration.py` — LLM zero-weight gate, regime-specific weights,
  determinism, fallbacks.
- `test_evaluation.py` — mandatory quant_only / llm_only / quant_plus_llm /
  baseline comparison.
- `test_fusion_storage.py` — atomic artifact/report persistence.
- `test_swappability.py` — FusedSignal stays separate from TradeProposal.

Note: `pythonpath = ["tests"]` in `pyproject.toml`, so these files import
`factories` directly. Test file basenames must stay unique across `tests/`
(e.g. `test_fusion_storage.py`, not `test_storage.py`, which collides with
`tests/unit/market_data/test_storage.py`).
