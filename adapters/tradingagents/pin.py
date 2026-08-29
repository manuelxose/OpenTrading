"""Pinned upstream identity for TauricResearch/TradingAgents (INV-14).

The adapter only talks to the exact upstream release recorded here and in
``external-lock.yaml``. Production never follows ``main`` / ``latest`` / ``HEAD``.
"""

from __future__ import annotations

__all__ = [
    "UPSTREAM_COMMIT",
    "UPSTREAM_LICENSE",
    "UPSTREAM_NAME",
    "UPSTREAM_REPOSITORY",
    "UPSTREAM_TAG",
    "UPSTREAM_VERSION",
]

UPSTREAM_NAME = "tradingagents"
UPSTREAM_REPOSITORY = "https://github.com/TauricResearch/TradingAgents"
UPSTREAM_LICENSE = "Apache-2.0"
UPSTREAM_VERSION = "0.3.1"
UPSTREAM_TAG = "v0.3.1"
UPSTREAM_COMMIT = "a33fd4c0f134485a43553a2c23a63cb14adbd88f"
