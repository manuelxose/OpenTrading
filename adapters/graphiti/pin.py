"""Pinned upstream identity for getzep/graphiti (INV-14).

The adapter only talks to the exact upstream release recorded here and in
``external-lock.yaml``. Production never follows ``main`` / ``latest`` / ``HEAD``.
"""

from __future__ import annotations

__all__ = [
    "UPSTREAM_DISTRIBUTION",
    "UPSTREAM_EXTRAS",
    "UPSTREAM_LICENSE",
    "UPSTREAM_REPOSITORY",
    "UPSTREAM_VERSION",
]

#: PyPI distribution name (checked via importlib.metadata).
UPSTREAM_DISTRIBUTION = "graphiti-core"
UPSTREAM_REPOSITORY = "https://github.com/getzep/graphiti"
UPSTREAM_LICENSE = "Apache-2.0"
UPSTREAM_VERSION = "0.29.3"
#: FalkorDB driver ships behind an extra (ADR-0008: FalkorDB first, Neo4j only
#: with a clear operational reason).
UPSTREAM_EXTRAS = ("falkordb",)
