# ADR-0019: Signal Fusion Engine — calibrated weights, signed components, regime-specific models

- Status: accepted
- Date: 2026-08-26
- Deciders: principal-architect (+ verification for risk-sensitive class)

## Context

INV-16 requires Signal Fusion with weights that are *calibrated, not arbitrary*:
always compare Quant-only / LLM-only / Quant+LLM / simple baseline, and reduce
or remove the LLM weight when the LLM adds no post-cost alpha. Phase 7
implements `engines/signal_fusion`. Implementing it surfaced three decisions the
frozen architecture does not answer:

1. How conflicting inputs (quant LONG vs LLM SHORT) are resolved.
2. How absent inputs are handled at fusion time.
3. Whether fused-component scores are unsigned magnitudes (as the Phase-0
   `FusedSignal` stub implied) or signed contributions.

## Decision

**Signed component scores.** `SignalComponent.score` becomes a signed
contribution in [-1, 1]: positive votes LONG, negative votes SHORT, zero
abstains. Component direction is derived from the sign. `FusedSignal` law:
`direction = sign(Σ wᵢ·scoreᵢ)` and `fused_strength = |Σ wᵢ·scoreᵢ|`; FLAT
requires exactly zero net score and zero strength. Signed scores let
disagreements be represented honestly instead of being fudged into positive
magnitudes.

**Configurable, calibrated weights.** `ComponentWeights` stores integer basis
points (sum exactly 10000). `FusionConfig` holds default weights, per-regime
weights, per-producer confidence maps, a disagreement policy and a missing-signal
policy. Calibration learns everything from labeled history:

- confidence calibration: pool-adjacent-violators isotonic regression of raw
  confidence against realized directional hit rate, per producer
  (`quant:<model_id>`, `llm:<model_name>`, `regime:<classifier_version>`,
  `memory:<memory_version>`);
- weights: deterministic grid search over basis-point compositions maximizing
  mean directional return, per regime when a regime has enough cases
  (fallback: weights learned on all cases);
- LLM value gate, applied per weight set: learned weights must beat the best
  LLM-free weights by at least `min_improvement`, otherwise the LLM weight is
  zero (INV-16).

**Disagreement policies** (`DisagreementPolicy`):

- `NEUTRALIZE` (default): linear combination, opposing scores cancel honestly;
- `TRUST_HIGHER_CONFIDENCE`: the disagreeing input with the highest calibrated
  confidence decides, the others abstain;
- `REQUIRE_CONSENSUS`: any directional conflict → FLAT signal.

Every conflict is recorded on the `FusedSignal` (`disagreements`).

**Missing-signal policies** (`MissingSignalPolicy`):

- `RENORMALIZE` (default): weights renormalize over the present inputs; when the
  calibration gives zero share to every present input, degrade deterministically
  to equal weights (never an error, never an arbitrary production weight);
- `REQUIRE_QUANT`: a missing `QuantSignal` means no fused signal at all.

Missing inputs are recorded on the `FusedSignal` (`missing_inputs`).

**Regime-specific models.** `FusionConfig.regime_weights` keys calibrated weight
sets by regime label; unknown/absent regimes fall back to `default_weights`.
Regime and memory inputs are advisory components (`RegimeContext`,
`MemoryContext`) that the calibrator can down-weight to zero like any other.

**Mandatory comparison and storage.** `evaluate_cases` always scores
quant_only / llm_only / quant_plus_llm / simple baseline (equal-weight average of
present inputs, raw confidences) with directional accuracy, mean directional
return, information ratio and binned calibration error (ECE). Calibration
artifacts (weights, confidence maps, train metrics, LLM-value decision, data
scope) are versioned by a deterministic hash of the training data and
hyperparameters, and persisted atomically by `CalibrationStore`
(`storage/calibration/signal_fusion/`); MLflow mirroring is optional and never
blocks persistence.

**Determinism.** The fusion engine is a pure function of its inputs, like the
Risk Engine: no wall clock, no IO, no LLM call. `signal_id` is UUIDv5 over the
canonical hash of inputs + configuration; the calibration version is a hash of
the training data + hyperparameters.

## Alternatives considered

- *Unsigned component magnitudes with positive-only fusion* — rejected: cannot
  represent opposing votes without distorting the weighted-sum law.
- *Hardcoded 0.5/0.3/0.2 weights* — rejected: violates INV-16.
- *Logistic-regression / learned-combination weights* — rejected for now: needs
  a heavier dependency surface; grid search over basis points is transparent,
  deterministic and auditable, and can be replaced later behind the same
  `FusionConfig` contract.
- *Error on zero-weight coverage* — rejected: graceful deterministic degradation
  (equal weights) is safer than failing a pipeline at runtime.
- *Single global LLM gate* — rejected: would remove a regime-specific LLM model
  that adds value in some regimes; the gate is applied per weight set.

## Consequences

- Positive: fusion is measurable, testable and swappable — it consumes only
  `FusionInputs` and emits only `FusedSignal`, and never imports risk or
  execution code; `FusedSignal` stays separate from `TradeProposal` (INV-1,
  INV-2).
- Positive: a calibration artifact fully reproduces every runtime decision
  (config is self-contained), and the LLM weight is provably zero when the LLM
  adds no measurable value.
- Negative: grid search is O(cases × weight combinations); fine for research
  datasets, revisit if calibration sets grow very large (the `Calibrator`
  interface hides the search).
- Follow-ups: Qlib/MLflow integration for experiment lineage; FX-rate feed for
  denomination of realized returns across instruments; leakage-aware walk-forward
  harness with purging/embargo before any weight is used on live capital.

## Validation

- `tests/unit/signal_fusion/`: conflicting signals under all three policies;
  missing LLM / missing Quant / REQUIRE_QUANT / empty inputs; extreme confidence
  (0, 1, NaN, out-of-range); deterministic configuration and calibration;
  noisy-LLM → zero weight, skilled-LLM → kept weight, regime-specific weights
  and fallback; mandatory four-config comparison and baseline equal weights;
  storage roundtrip and atomic index; separation from `TradeProposal`.
- `make ci` green (lint + mypy strict + full pytest suite).
