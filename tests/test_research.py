"""Research providers: provenance, caching, failure behavior."""

import io
import json
import urllib.error

import pytest

from domain.enums import EvidenceType
from evidence.validation import validate_item
from research import (
    CachedResearchProvider,
    MockResearchProvider,
    ResearchAuthError,
    ResearchBundle,
    ResearchProvider,
    ResearchQuery,
    ResearchResult,
    ResearchUnavailableError,
    TavilyResearchProvider,
    research_to_evidence,
)


def _bundle() -> ResearchBundle:
    from datetime import datetime, timezone

    moment = datetime(2026, 5, 1, tzinfo=timezone.utc)
    return ResearchBundle(
        query="packaging PEP 685 extras",
        results=[
            ResearchResult(
                id="r1", query="q", source="https://github.com/pypa/packaging/issues/545",
                title="Adhere to PEP 685", snippet="markers", url="https://x/545",
                content_hash="a" * 64, retrieved_at=moment,
            )
        ],
        retrieved_at=moment,
    )


def test_mock_serves_fixtures_and_empty_for_unknown():
    provider = MockResearchProvider({"packaging PEP 685": _bundle()})
    assert isinstance(provider, ResearchProvider)
    found = provider.search(ResearchQuery(query="  packaging pep 685 "))
    assert len(found.results) == 1 and not found.cached
    missing = provider.search(ResearchQuery(query="something unheard of"))
    assert missing.results == []
    assert provider.calls == ["packaging pep 685", "something unheard of"]


def test_cache_marks_hits_and_avoids_repeated_calls():
    inner = MockResearchProvider({"q": _bundle()})
    cached = CachedResearchProvider(inner)
    first = cached.search(ResearchQuery(query="q"))
    second = cached.search(ResearchQuery(query="Q "))
    assert not first.cached and second.cached
    assert first.results == second.results
    assert len(inner.calls) == 1
    assert cached.size == 1
    cached.clear()
    assert cached.size == 0
    with pytest.raises(ValueError):
        CachedResearchProvider(inner, max_entries=0)


def test_tavily_requires_credentials():
    provider = TavilyResearchProvider(api_key="")
    assert isinstance(provider, ResearchProvider)
    assert not provider.configured
    with pytest.raises(ResearchAuthError):
        provider.search(ResearchQuery(query="q"))


def test_tavily_parses_results_with_provenance():
    def opener(request, timeout):
        body = json.dumps(
            {
                "results": [
                    {
                        "url": "https://github.com/pypa/packaging/issues/545",
                        "title": "Adhere to PEP 685",
                        "content": "markers with extras",
                        "score": 0.9,
                    },
                    "junk-entry",
                    {"url": "https://x", "title": "t", "content": "c", "score": "high"},
                ]
            }
        )
        return io.BytesIO(body.encode())

    provider = TavilyResearchProvider(api_key="k", opener=opener)
    bundle = provider.search(ResearchQuery(query="pep 685", top_k=5))
    assert len(bundle.results) == 1
    result = bundle.results[0]
    assert result.url.endswith("/545") and len(result.content_hash) == 64
    assert result.score == 0.9


def test_tavily_rejects_bad_endpoints():
    with pytest.raises(ValueError):
        TavilyResearchProvider(api_key="k", endpoint="http://plain.example/search")


def test_cache_separates_top_k_variants():
    seen = []

    class CountingProvider:
        def search(self, query):
            seen.append((query.query, query.top_k))
            return ResearchBundle(query=query.query, results=[])

    cached = CachedResearchProvider(CountingProvider())
    cached.search(ResearchQuery(query="q", top_k=1))
    cached.search(ResearchQuery(query="q", top_k=5))
    assert seen == [("q", 1), ("q", 5)]
    assert cached.size == 2


def test_tavily_failures_are_typed():
    def auth_opener(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 401, "no", {}, io.BytesIO())

    with pytest.raises(ResearchAuthError):
        TavilyResearchProvider(api_key="k", opener=auth_opener).search(
            ResearchQuery(query="q")
        )

    def down_opener(request, timeout):
        raise urllib.error.URLError("down")

    with pytest.raises(ResearchUnavailableError):
        TavilyResearchProvider(api_key="k", opener=down_opener).search(
            ResearchQuery(query="q")
        )

    def junk_opener(request, timeout):
        return io.BytesIO(b"{}")

    empty = TavilyResearchProvider(api_key="k", opener=junk_opener).search(
        ResearchQuery(query="q")
    )
    assert empty.results == []


def test_research_to_evidence_carries_provenance():
    items = research_to_evidence(_bundle(), claim_prefix="release research")
    assert len(items) == 1
    item = items[0]
    assert item.evidence_type == EvidenceType.SEARCH_RESULT
    assert item.artifact_ref == "https://x/545"
    assert item.payload["query"] == "packaging PEP 685 extras"
    assert item.payload["content_hash"] == "a" * 64
    assert validate_item(item).valid
