"""Tests for API integrations, safe environment loading, and read-only GitHub client."""

from __future__ import annotations

import io
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

import pytest

from env_config import load_env
from github.client import GitHubReadOnlyError, ReadOnlyGitHubClient
from github.errors import GitHubAuthError, GitHubNotFoundError
from reasoning.errors import ReasoningAuthError, ReasoningMalformedError
from reasoning.nebius import NebiusReasoningProvider
from research.models import ResearchAuthError, ResearchQuery
from research.tavily import TavilyResearchProvider
from tracing import get_default_tracer
from tracing.langsmith import LangSmithTracer
from tracing.local import LocalTracer


# =========================================================================
# Phase 1: Environment Loading & Safety
# =========================================================================

def test_load_env_populates_new_vars_and_preserves_existing(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TEST_NEW_VAR=hello_world\n"
        "TEST_PREEXISTING_VAR=from_file\n"
        "# Comment line\n"
        "TEST_QUOTED=\"with_quotes\"\n"
        "MALFORMED_LINE\n",
        encoding="utf-8",
    )
    os.environ["TEST_PREEXISTING_VAR"] = "from_process"
    try:
        loaded = load_env(env_file)
        assert loaded["TEST_NEW_VAR"] == "hello_world"
        assert loaded["TEST_QUOTED"] == "with_quotes"
        assert "TEST_PREEXISTING_VAR" not in loaded
        assert os.environ["TEST_PREEXISTING_VAR"] == "from_process"
        assert os.environ["TEST_NEW_VAR"] == "hello_world"
    finally:
        os.environ.pop("TEST_NEW_VAR", None)
        os.environ.pop("TEST_PREEXISTING_VAR", None)
        os.environ.pop("TEST_QUOTED", None)


def test_load_env_missing_file_fails_safely(tmp_path):
    missing_file = tmp_path / "nonexistent.env"
    loaded = load_env(missing_file)
    assert loaded == {}


# =========================================================================
# Phase 2: Nebius/Nemotron Provider Mocked Tests
# =========================================================================

def test_nebius_missing_credentials_raises_auth_error():
    provider = NebiusReasoningProvider(api_key="", model="")
    with pytest.raises(ReasoningAuthError, match="NEBIUS_API_KEY is not set"):
        provider.analyze_upstream(issue_id="issue:1", title="test")

    provider2 = NebiusReasoningProvider(api_key="valid_key", model="")
    with pytest.raises(ReasoningAuthError, match="NEBIUS_MODEL is not set"):
        provider2.analyze_upstream(issue_id="issue:1", title="test")


def test_nebius_rejects_non_https():
    with pytest.raises(ValueError, match="must be an https:// URL"):
        NebiusReasoningProvider(
            api_key="k", model="m", base_url="http://insecure.endpoint.com"
        )


def test_nebius_secrets_not_leaked_in_exceptions():
    def failing_opener(request, timeout):
        raise urllib.error.HTTPError(
            url=request.full_url,
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=io.BytesIO(b'{"error": "unauthorized"}'),
        )

    secret_key = "secret_nebius_key_sentinel_xyz"
    provider = NebiusReasoningProvider(
        api_key=secret_key,
        model="Nemotron-3-Ultra-550b-a55b-serverless",
        opener=failing_opener,
    )
    with pytest.raises(ReasoningAuthError) as exc_info:
        provider.analyze_upstream(issue_id="issue:1", title="test")
    assert secret_key not in str(exc_info.value)


def test_nebius_output_never_authorizes_or_claims_verified():
    def mock_opener(request, timeout):
        # Even if the model maliciously returns verified: true
        body = json.dumps({
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "issue_id": "issue:1",
                        "summary": "analysis summary",
                        "verified": True,
                        "uncertainties": [],
                    })
                }
            }]
        })
        return io.BytesIO(body.encode("utf-8"))

    provider = NebiusReasoningProvider(
        api_key="k",
        model="Nemotron-3-Ultra-550b-a55b-serverless",
        opener=mock_opener,
    )
    res = provider.analyze_upstream(issue_id="issue:1", title="test")
    # Invariant: verified MUST ALWAYS be False
    assert res.verified is False


# =========================================================================
# Phase 3: Tavily Provider Mocked Tests
# =========================================================================

def test_tavily_missing_credentials_raises_auth_error():
    provider = TavilyResearchProvider(api_key="")
    with pytest.raises(ResearchAuthError, match="TAVILY_API_KEY is not set"):
        provider.search(ResearchQuery(query="packaging PEP 685"))


def test_tavily_mock_search_preserves_provenance():
    def mock_opener(request, timeout):
        payload = {
            "results": [
                {
                    "title": "PEP 685 - Comparison of extra names",
                    "url": "https://peps.python.org/pep-0685/",
                    "content": "Normalization of extra names in packaging requirements.",
                    "score": 0.95,
                }
            ]
        }
        return io.BytesIO(json.dumps(payload).encode("utf-8"))

    provider = TavilyResearchProvider(api_key="test_tavily_key", opener=mock_opener)
    bundle = provider.search(ResearchQuery(query="PEP 685"))
    assert len(bundle.results) == 1
    assert bundle.results[0].title == "PEP 685 - Comparison of extra names"
    assert bundle.results[0].content_hash
    assert bundle.results[0].url == "https://peps.python.org/pep-0685/"


# =========================================================================
# Phase 4: LangSmith Tracing Scrubbing & Config Tests
# =========================================================================

def test_tracing_selector():
    old_key = os.environ.get("LANGSMITH_API_KEY")
    try:
        os.environ.pop("LANGSMITH_API_KEY", None)
        assert isinstance(get_default_tracer(), LocalTracer)

        os.environ["LANGSMITH_API_KEY"] = "some_key"
        assert isinstance(get_default_tracer(), LangSmithTracer)
    finally:
        if old_key is not None:
            os.environ["LANGSMITH_API_KEY"] = old_key
        else:
            os.environ.pop("LANGSMITH_API_KEY", None)


def test_langsmith_scrubs_sentinel_secrets_before_buffering():
    tracer = LangSmithTracer(api_key="dummy_api_key")
    with tracer.span("trace:1", "test.span", secret_attr="ghp_0123456789abcdefghij"):
        pass
    events = tracer.events()
    assert len(events) == 1
    attrs_str = str(events[0].attributes)
    assert "ghp_0123456789abcdefghij" not in attrs_str
    assert "[redacted]" in attrs_str


# =========================================================================
# Phase 5: ReadOnlyGitHubClient Tests
# =========================================================================

def test_readonly_github_client_blocks_mutations():
    client = ReadOnlyGitHubClient(token="mock_token")
    with pytest.raises(GitHubReadOnlyError, match="Mutations are forbidden"):
        client.create_branch("org/repo", "test-branch", "0" * 40)

    with pytest.raises(GitHubReadOnlyError, match="Mutations are forbidden"):
        client.create_commit("org/repo", "main", "commit msg", {})

    with pytest.raises(GitHubReadOnlyError, match="Mutations are forbidden"):
        client.create_pull_request("org/repo", "title", "body", "head", "base")


def test_readonly_github_client_reads_repository_and_issue():
    def mock_opener(request, timeout):
        url = request.full_url
        if "/repos/pypa/packaging/issues/545" in url:
            data = {
                "id": 12345,
                "number": 545,
                "title": "Fix PEP 685 extra comparison",
                "body": "Normalized extra comparison in markers",
                "state": "closed",
                "created_at": "2022-04-10T12:00:00Z",
            }
        elif "/repos/pypa/packaging" in url:
            data = {
                "id": 999,
                "full_name": "pypa/packaging",
                "default_branch": "main",
            }
        else:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, io.BytesIO(b"{}"))
        return io.BytesIO(json.dumps(data).encode("utf-8"))

    client = ReadOnlyGitHubClient(token="mock_token", opener=mock_opener)
    repo = client.get_repository("pypa/packaging")
    assert repo.full_name == "pypa/packaging"
    assert repo.default_branch == "main"

    issue = client.get_issue("pypa/packaging", 545)
    assert issue.number == 545
    assert issue.title == "Fix PEP 685 extra comparison"
    assert issue.state.value == "CLOSED"
