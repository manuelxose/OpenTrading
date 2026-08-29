"""Adapter-owned values; no RD-Agent class crosses this module boundary."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Hypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["factor", "model"]
    title: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Implementation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["factor", "model"]
    name: str = Field(min_length=1)
    code: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    llm_metadata: dict[str, Any] = Field(default_factory=dict)
