"""Deterministic research cache + offline mock (Phase 3).

The cache keys on the normalized query, marks hits as cached, and never
expires entries implicitly (explicit ``clear()``) so runs stay
deterministic. The mock serves fixture bundles for known queries and
empty (never fabricated) bundles otherwise.
"""

from __future__ import annotations

from research.base import ResearchProvider
from research.models import ResearchBundle, ResearchQuery


def _normalize(query: str) -> str:
    return " ".join(query.strip().lower().split())


def _cache_key(query: ResearchQuery) -> tuple[str, int, str]:
    return (_normalize(query.query), query.top_k, (query.topic or "general").strip().lower())


class CachedResearchProvider(ResearchProvider):
    """Memoizing wrapper: repeat queries never hit the network twice."""

    def __init__(self, inner: ResearchProvider, *, max_entries: int = 256) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self._inner = inner
        self._max_entries = max_entries
        self._cache: dict[tuple[str, int, str], ResearchBundle] = {}

    def search(self, query: ResearchQuery) -> ResearchBundle:
        key = _cache_key(query)
        hit = self._cache.get(key)
        if hit is not None:
            return hit.model_copy(deep=True, update={"cached": True})
        bundle = self._inner.search(query)
        if len(self._cache) >= self._max_entries:
            oldest = next(iter(self._cache))
            del self._cache[oldest]
        stored = bundle.model_copy(update={"cached": False})
        self._cache[key] = stored
        return stored.model_copy(deep=True)

    def clear(self) -> None:
        self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)


class MockResearchProvider(ResearchProvider):
    """Fixture-backed research for tests (offline, no credentials)."""

    def __init__(self, fixtures: dict[str, ResearchBundle] | None = None) -> None:
        self._fixtures = {_normalize(k): v for k, v in (fixtures or {}).items()}
        self.calls: list[str] = []

    def search(self, query: ResearchQuery) -> ResearchBundle:
        self.calls.append(query.query)
        bundle = self._fixtures.get(_normalize(query.query))
        if bundle is None:
            return ResearchBundle(query=query.query, results=[])
        refreshed = bundle.model_copy(deep=True, update={"query": query.query})
        for result in refreshed.results:
            result.query = query.query
        return refreshed


__all__ = ["CachedResearchProvider", "MockResearchProvider"]
