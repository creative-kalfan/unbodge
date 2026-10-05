"""Research providers: Tavily, cache, mock, evidence bridge (Phase 3)."""

from research.base import ResearchProvider
from research.cache import CachedResearchProvider, MockResearchProvider
from research.evidence import research_to_evidence
from research.models import (
    ResearchAuthError,
    ResearchBundle,
    ResearchError,
    ResearchQuery,
    ResearchResult,
    ResearchUnavailableError,
)
from research.tavily import TAVILY_ENDPOINT, TavilyResearchProvider

__all__ = [
    "TAVILY_ENDPOINT",
    "CachedResearchProvider",
    "MockResearchProvider",
    "ResearchAuthError",
    "ResearchBundle",
    "ResearchError",
    "ResearchProvider",
    "ResearchQuery",
    "ResearchResult",
    "ResearchUnavailableError",
    "TavilyResearchProvider",
    "research_to_evidence",
]
