"""Production API models (Phase 4). Thin I/O schemas over domain contracts."""

from __future__ import annotations

from domain.models import UnbodgeModel
from pydantic import Field


class RepositoryIn(UnbodgeModel):
    full_name: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class RepositoryOut(UnbodgeModel):
    id: str = Field(min_length=1)
    full_name: str = Field(min_length=1)


class EventIn(UnbodgeModel):
    repository_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=512)
    body: str = Field(default="", max_length=8192)
    source: str = Field(default="github", max_length=64)


class DecisionOut(UnbodgeModel):
    id: str = Field(min_length=1)
    outcome: str = Field(min_length=1)
    rationale: str = ""


class ErrorOut(UnbodgeModel):
    detail: str = Field(min_length=1)


__all__ = ["DecisionOut", "ErrorOut", "EventIn", "RepositoryIn", "RepositoryOut"]
