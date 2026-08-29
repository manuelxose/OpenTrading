# engines/signal_fusion — Signal Fusion Engine (Phase 7, INV-16)

Fuses `QuantSignal` / `LLMSignal` / `RegimeContext` / `MemoryContext` into
`core.schemas.FusedSignal`. Weights derive from historical calibration — never
arbitrary — and are always compared against Quant-only / LLM-only / Quant+LLM /
simple baseline. The LLM gets zero weight when it adds no measurable value.

## Modules

| Module | Responsibility |
|---|---|
| `config.py` | `ComponentWeights` (integer basis points), `ConfidenceMap`, `FusionConfig`, disagreement/missing-signal policies |
| `fusion.py` | Deterministic `fuse_signals` / `FusionEngine` — pure function of inputs (INV-4 style) |
| `isotonic.py` | PAV isotonic regression for confidence calibration (no external deps) |
| `calibration.py` | `Calibrator` — confidence maps, grid-searched weights, regime-specific models, LLM-value gate, `CalibrationArtifact` |
| `evaluation.py` | `evaluate_cases` — mandatory four-config comparison with deterministic metrics |
| `storage.py` | `CalibrationStore` — atomic JSON persistence of artifacts, evaluations and index; optional MLflow mirror |
| `errors.py` | `FusionError` / `CalibrationError` hierarchy |

## Fusion law

Each present input contributes a signed score: `+strength` (LONG), `-strength`
(SHORT), `0` (FLAT/abstain). Then:

```text
net      = Σ wᵢ · scoreᵢ            (weights renormalized over present inputs)
direction = sign(net)              (|net| < flat_threshold → FLAT, scores zeroed)
strength = |net|
confidence = Σ wᵢ · ĉᵢ            (per-producer calibrated confidence)
```

Weights are basis-point integers (sum exactly 10000). Disagreements are recorded
on the signal and resolved per `DisagreementPolicy`; missing inputs are recorded
and handled per `MissingSignalPolicy` (ADR-0019).

## Usage

```python
from core.schemas.fusion import FusionInputs
from engines.signal_fusion import FusionConfig, ComponentWeights, fuse_signals

config = FusionConfig(
    name="eurusd",
    version="cal-<hash>",
    default_weights=ComponentWeights(quant_bp=6000, llm_bp=3000, regime_bp=1000, memory_bp=0),
)
fused = fuse_signals(
    inputs=FusionInputs(quant=quant_signal, llm=llm_signal), config=config, produced_at=clock.now()
)
```

## Calibration & research evaluation

```python
calibrator = Calibrator(
    weight_step_bp=500, min_cases_per_regime=20, min_cases_confidence=10, min_improvement=0.0
)
artifact = calibrator.calibrate(train_cases, name="eurusd", trained_at=clock.now())
report = evaluate_cases(test_cases, config=artifact.config, evaluated_at=clock.now())

store = CalibrationStore()  # storage/calibration/signal_fusion
store.save_artifact(artifact)
store.save_evaluation(report)
```

- `LabeledFusionCase(inputs, realized_return, as_of)` labels history.
- The LLM-value gate compares learned weights against the best LLM-free weights
  per weight set; below `min_improvement` the LLM weight is zero.
- `evaluate_cases` scores quant_only / llm_only / quant_plus_llm / baseline
  (equal-weight average, raw confidences) with accuracy, mean directional
  return, information ratio and binned ECE.

## Guarantees

- Deterministic: same inputs + config → identical `FusedSignal` (same id, same
  JSON); same training data + hyperparameters → identical calibration version.
- Swappable: the engine consumes only `FusionInputs` and emits only
  `FusedSignal`; it never imports risk or execution code (INV-1, INV-2).
- No arbitrary production weights: every weight in a `FusionConfig` comes from
  calibration or from the documented equal-weight degradation fallback.

See `docs/ADR/0019-signal-fusion-calibrated-weights.md`.

