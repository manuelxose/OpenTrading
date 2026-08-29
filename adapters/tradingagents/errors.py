"""TradingAgents adapter errors.

Concrete error types so callers can distinguish "upstream missing", "pin
violated", "budget exhausted" and "translation failed" without string matching.
Every failure mode is an :class:`TradingAgentsError` — upstream exceptions never
escape the adapter boundary.
"""

from __future__ import annotations

__all__ = [
    "TradingAgentsError",
    "TradingAgentsMappingError",
    "TradingAgentsTimeoutError",
    "TradingAgentsUnavailableError",
    "TradingAgentsVersionError",
]


class TradingAgentsError(Exception):
    """Base class for every TradingAgents adapter error."""


class TradingAgentsUnavailableError(TradingAgentsError):
    """Upstream cannot be imported or instantiated (not installed / broken)."""


class TradingAgentsVersionError(TradingAgentsError):
    """The installed upstream version violates the pinned version/commit."""


class TradingAgentsTimeoutError(TradingAgentsError):
    """The upstream run exceeded the adapter's timeout budget."""


class TradingAgentsMappingError(TradingAgentsError):
    """A domain input could not be translated to upstream, or an upstream output
    could not be translated back to the canonical :class:`LLMSignal` contract."""
