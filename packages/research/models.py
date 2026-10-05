"""Research contracts (Phase 3).

Search results are EVIDENCE INPUTS, never truth. Every result carries
structured provenance: query, source, metadata, timestamp, and a content
hash. Cached results are marked as such.
"""

from __future__ import annotations

from domain.errors import UnbodgeError
from domain.models import UnbodgeModel, utcnow
from pydantic import Field
from datetime import datetime


class ResearchError(UnbodgeError):
    """Base class for research provider failures."""


class ResearchAuthError(ResearchError):
    """Missing/invalid research credentials."""


class ResearchUnavailableError(ResearchError):
    """Provider unreachable, throttled, or misbehaving (never fabricated)."""


class ResearchQuery(UnbodgeModel):
    query: str = Field(min_length=1, max_length=512)
    top_k: int = Field(default=5, ge=1, le=20)
    topic: str = ""


class ResearchResult(UnbodgeModel):
    id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    source: str = Field(min_length=1)
    title: str = ""
    snippet: str = ""
    url: str = ""
    published_at: datetime | None = None
    score: float = Field(default=0.0, ge=0.0)
    content_hash: str = ""
    retrieved_at: datetime = Field(default_factory=utcnow)
    cached: bool = False


class ResearchBundle(UnbodgeModel):
    query: str = Field(min_length=1)
    results: list[ResearchResult] = Field(default_factory=list)
    cached: bool = False
    retrieved_at: datetime = Field(default_factory=utcnow)


__all__ = [
    "ResearchBundle",
    "ResearchError",
    "ResearchAuthError",
    "ResearchQuery",
    "ResearchResult",
    "ResearchUnavailableError",
]
