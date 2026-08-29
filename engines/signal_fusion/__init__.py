"""Signal Fusion Engine (architecture §16, INV-16) — implemented in Phase 7.

Fuses quant / LLM / regime / memory inputs into ``core.schemas.FusedSignal``
with weights that are *calibrated from labeled history*, never arbitrary. The
mandatory baselines (quant_only / llm_only / quant_plus_llm / simple baseline)
are always compared, and the LLM gets zero weight when it adds no measurable
value.

The engine is deterministic and swappable: it consumes only ``FusionInputs``
and emits only ``FusedSignal`` — it never imports risk or execution code, and
``FusedSignal`` stays separate from ``TradeProposal`` (INV-1, INV-2).
"""

from engines.signal_fusion.calibration import (
    CalibrationArtifact,
    Calibrator,
    DataScope,
    calibrate,
)
from engines.signal_fusion.config import (
    COMPONENT_NAMES,
    ComponentWeights,
    ConfidenceMap,
    DisagreementPolicy,
    FusionConfig,
    MissingSignalPolicy,
)
from engines.signal_fusion.errors import (
    CalibrationError,
    CalibrationInsufficientDataError,
    FusionConfigurationError,
    FusionError,
)
from engines.signal_fusion.evaluation import (
    ConfigMetrics,
    EvaluationReport,
    LabeledFusionCase,
    evaluate_cases,
)
from engines.signal_fusion.fusion import (
    FUSION_ENGINE_VERSION,
    FusionEngine,
    fuse_signals,
)
from engines.signal_fusion.storage import CalibrationStore

__all__ = [
    "COMPONENT_NAMES",
    "FUSION_ENGINE_VERSION",
    "CalibrationArtifact",
    "CalibrationError",
    "CalibrationInsufficientDataError",
    "CalibrationStore",
    "Calibrator",
    "ComponentWeights",
    "ConfidenceMap",
    "ConfigMetrics",
    "DataScope",
    "DisagreementPolicy",
    "EvaluationReport",
    "FusionConfig",
    "FusionConfigurationError",
    "FusionEngine",
    "FusionError",
    "LabeledFusionCase",
    "MissingSignalPolicy",
    "calibrate",
    "evaluate_cases",
    "fuse_signals",
]
