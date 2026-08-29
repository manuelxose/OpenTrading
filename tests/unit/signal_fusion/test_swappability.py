"""Definition of Done: fusion is swappable and stays separate from trading/risk.

``FusedSignal`` must remain separate from ``TradeProposal``, and the fusion
engine must not import risk or execution code — so it can be swapped without
touching them.
"""

from __future__ import annotations

import inspect

import engines.signal_fusion.calibration
import engines.signal_fusion.config
import engines.signal_fusion.evaluation
import engines.signal_fusion.fusion
import engines.signal_fusion.isotonic
import engines.signal_fusion.storage
from core.schemas import FusedSignal
from core.schemas.trading import TradeProposal

ENGINE_MODULES = [
    engines.signal_fusion.calibration,
    engines.signal_fusion.config,
    engines.signal_fusion.evaluation,
    engines.signal_fusion.fusion,
    engines.signal_fusion.isotonic,
    engines.signal_fusion.storage,
]


class TestSeparationFromTrading:
    def test_fused_signal_is_a_distinct_contract(self) -> None:
        assert FusedSignal is not TradeProposal
        assert not issubclass(FusedSignal, TradeProposal)
        assert not issubclass(TradeProposal, FusedSignal)
        # No order/sizing fields leak into the fused signal.
        assert "quantity" not in FusedSignal.model_fields
        assert "limit_price" not in FusedSignal.model_fields
        assert "stop_loss" not in FusedSignal.model_fields

    def test_fusion_engine_does_not_import_trading_or_risk(self) -> None:
        for module in ENGINE_MODULES:
            source = inspect.getsource(module)
            assert "schemas.trading" not in source, module.__name__
            assert "schemas.risk" not in source, module.__name__
            assert "engines.risk" not in source, module.__name__
            assert "adapters." not in source, module.__name__

    def test_fused_signal_flows_without_trade_proposal(self) -> None:
        """A fused signal can be produced and consumed with no proposal in sight."""
        from datetime import UTC, datetime

        from core.schemas.fusion import FusionInputs
        from engines.signal_fusion.config import ComponentWeights, FusionConfig
        from engines.signal_fusion.fusion import fuse_signals

        from factories import make_llm_signal, make_quant_signal

        t = datetime(2026, 1, 5, 10, 0, 0, tzinfo=UTC)
        config = FusionConfig(
            name="standalone",
            version="cal-standalone-1",
            default_weights=ComponentWeights(quant_bp=7000, llm_bp=3000, regime_bp=0, memory_bp=0),
        )
        fused = fuse_signals(
            inputs=FusionInputs(
                quant=make_quant_signal(t),
                llm=make_llm_signal(t),
            ),
            config=config,
            produced_at=t,
        )
        assert fused is not None
        assert isinstance(fused, FusedSignal)
        assert not isinstance(fused, TradeProposal)
