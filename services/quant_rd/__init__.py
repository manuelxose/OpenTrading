"""Autonomous research service; deliberately separate from the core runtime."""

from services.quant_rd.policy import ResearchAuthorityPolicy, ResearchBoundaryViolation

__all__ = ["ResearchAuthorityPolicy", "ResearchBoundaryViolation"]
