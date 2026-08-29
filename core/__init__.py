"""OpenTrading core runtime — Phase 0 Foundations.

The domain layer in this package imports no external trading framework
(TradingAgents, MT4, Qlib, Graphiti, Nautilus). That property is enforced by a test
(``tests/unit/domain/test_import_guard.py``).
"""

from core.schemas.base import SCHEMA_VERSION

__version__ = "0.1.0"

__all__ = ["SCHEMA_VERSION", "__version__"]
