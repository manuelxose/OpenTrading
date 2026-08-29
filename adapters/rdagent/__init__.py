"""Typed boundary around Microsoft RD-Agent (offline research only)."""

from adapters.rdagent.adapter import RDAgentAdapter, RDAgentBackend
from adapters.rdagent.native import NativeRDAgentQlibBackend
from adapters.rdagent.schemas import Hypothesis, Implementation

__all__ = [
    "Hypothesis",
    "Implementation",
    "NativeRDAgentQlibBackend",
    "RDAgentAdapter",
    "RDAgentBackend",
]
