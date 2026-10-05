"""Reasoning providers: mock behavior, shared interface, failure taxonomy."""

import inspect
import io
import json
import urllib.error

import pytest

from reasoning.base import ReasoningProvider
from reasoning.errors import (
    ReasoningAuthError,
    ReasoningError,
    ReasoningMalformedError,
    ReasoningRateLimitError,
    ReasoningUnavailableError,
)
from reasoning.mock import MockReasoningProvider
from reasoning.models import ReasoningStatus, SynthesisAssessment
from reasoning.nebius import NebiusReasoningProvider

OPERATIONS = (
    "analyze_upstream",
    "analyze_workaround",
    "generate_reproduction",
    "synthesize_evidence",
)


def test_both_providers_share_the_interface():
    assert isinstance(MockReasoningProvider(), ReasoningProvider)
    assert isinstance(
        NebiusReasoningProvider(api_key="k", model="m"), ReasoningProvider
    )
    mock_signatures = {
        name: inspect.signature(getattr(MockReasoningProvider, name)) for name in OPERATIONS
    }
    nebius_signatures = {
        name: inspect.signature(getattr(NebiusReasoningProvider, name)) for name in OPERATIONS
    }
    assert mock_signatures == nebius_signatures


def test_mock_returns_deterministic_unverified_proposals():
    provider = MockReasoningProvider()
    first = provider.analyze_upstream(issue_id="issue:545", title="t", body="b")
    second = provider.analyze_upstream(issue_id="issue:545", title="t", body="b")
    assert first == second
    assert first.verified is False
    assert first.status == ReasoningStatus.UNCERTAIN
    assert first.uncertainties
    assert provider.analyze_workaround(file_path="f.py", snippet="s").verified is False
    plan = provider.generate_reproduction(hypothesis_id="h", claim="c")
    assert plan.commands and plan.verified is False
    synthesis = provider.synthesize_evidence(hypothesis_id="h", evidence_ids=["e1"])
    assert synthesis.assessment == SynthesisAssessment.INSUFFICIENT
    assert synthesis.verified is False


def test_mock_rejects_empty_inputs():
    provider = MockReasoningProvider()
    with pytest.raises(ValueError):
        provider.analyze_upstream(issue_id="  ", title="t")
    with pytest.raises(ValueError):
        provider.generate_reproduction(hypothesis_id="h", claim="  ")


def _opener_for(payload: dict):
    def opener(request, timeout):
        body = json.dumps({"choices": [{"message": {"content": json.dumps(payload)}}]})
        return io.BytesIO(body.encode())

    return opener


def _upstream_payload():
    return {
        "issue_id": "issue:545",
        "summary": "markers ignore PEP 685",
        "uncertainties": [],
        "status": "OK",
        "verified": False,
    }


def test_nebius_parses_structured_output_without_network():
    provider = NebiusReasoningProvider(
        api_key="test-key", model="test-model", opener=_opener_for(_upstream_payload())
    )
    assert provider.configured
    result = provider.analyze_upstream(issue_id="issue:545", title="t")
    assert result.issue_id == "issue:545"
    assert result.verified is False


def test_nebius_forces_unverified_even_if_model_claims_proof():
    payload = dict(_upstream_payload(), verified=True, status="OK", uncertainties=[])
    provider = NebiusReasoningProvider(
        api_key="k", model="m", opener=_opener_for(payload)
    )
    result = provider.analyze_upstream(issue_id="i", title="t")
    assert result.verified is False


def test_nebius_maps_timeouts_and_validates_inputs():
    import socket

    def opener(request, timeout):
        raise socket.timeout("slow")

    from reasoning.errors import ReasoningTimeoutError

    provider = NebiusReasoningProvider(api_key="k", model="m", opener=opener)
    with pytest.raises(ReasoningTimeoutError):
        provider.analyze_upstream(issue_id="i", title="t")
    live = NebiusReasoningProvider(api_key="k", model="m", opener=_opener_for({}))
    with pytest.raises(ValueError):
        live.analyze_upstream(issue_id="  ", title="t")
    with pytest.raises(ValueError):
        live.synthesize_evidence(hypothesis_id="", evidence_ids=[])


def test_nebius_rejects_non_https_endpoints():
    with pytest.raises(ValueError):
        NebiusReasoningProvider(api_key="k", model="m", base_url="http://evil.example")
    with pytest.raises(ValueError):
        NebiusReasoningProvider(api_key="k", model="m", base_url="https://user@host")


def test_nebius_requires_configuration():
    provider = NebiusReasoningProvider(api_key="", model="")
    assert not provider.configured
    with pytest.raises(ReasoningAuthError):
        provider.analyze_upstream(issue_id="i", title="t")
    with pytest.raises(ReasoningAuthError):
        NebiusReasoningProvider(api_key="k", model="").synthesize_evidence(
            hypothesis_id="h", evidence_ids=[]
        )


def test_nebius_rejects_invalid_structured_output():
    provider = NebiusReasoningProvider(
        api_key="k", model="m", opener=_opener_for({"wrong": "shape"})
    )
    with pytest.raises(ReasoningMalformedError):
        provider.analyze_upstream(issue_id="i", title="t")


def test_nebius_rejects_garbage_envelope():
    def opener(request, timeout):
        return io.BytesIO(b"not json")

    provider = NebiusReasoningProvider(api_key="k", model="m", opener=opener)
    with pytest.raises(ReasoningMalformedError):
        provider.analyze_upstream(issue_id="i", title="t")


@pytest.mark.parametrize(
    "code,error",
    [
        (401, ReasoningAuthError),
        (403, ReasoningAuthError),
        (429, ReasoningRateLimitError),
        (404, ReasoningUnavailableError),
        (500, ReasoningUnavailableError),
    ],
)
def test_nebius_http_failures_are_typed(code, error):
    def opener(request, timeout):
        raise urllib.error.HTTPError(request.full_url, code, "err", {}, io.BytesIO())

    provider = NebiusReasoningProvider(api_key="k", model="m", opener=opener)
    with pytest.raises(error):
        provider.analyze_workaround(file_path="f", snippet="s")


def test_nebius_transport_failure_is_unavailable():
    def opener(request, timeout):
        raise urllib.error.URLError("dns down")

    provider = NebiusReasoningProvider(api_key="k", model="m", opener=opener)
    with pytest.raises(ReasoningUnavailableError):
        provider.generate_reproduction(hypothesis_id="h", claim="c")


def test_reasoning_errors_are_unbodge_errors():
    from domain.errors import UnbodgeError

    assert issubclass(ReasoningError, UnbodgeError)
