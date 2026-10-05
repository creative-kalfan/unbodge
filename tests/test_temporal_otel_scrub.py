"""Temporal mapping, OTel spans, secret scrubbing."""

import pytest

from domain.enums import EvidenceType
from evidence import ScrubbedEvidence, scrub_item, scrub_text
from evidence.items import make_evidence
from tracing import LocalTracer, OtelTracer
from workflow import (
    ACTIVITIES,
    LocalWorkflowRunner,
    RetryPolicy,
    STAGE_NAMES,
    TemporalUnavailableError,
    TemporalWorkflowRunner,
    WORKFLOW_NAME,
)


def test_activities_cover_all_stages_in_order():
    assert [a.name for a in ACTIVITIES] == list(STAGE_NAMES)
    assert WORKFLOW_NAME == "unbodge-proof-loop"
    assert all(a.version == "v1" and a.max_retries >= 1 for a in ACTIVITIES)
    with pytest.raises(ValueError):
        LocalWorkflowRunner(activities=ACTIVITIES[:3])


def test_local_runner_delegates_to_pipeline():
    runner = LocalWorkflowRunner()
    assert runner.activities == ACTIVITIES
    policy = RetryPolicy(max_attempts=2)
    assert policy.max_attempts == 2


def test_temporal_runner_fails_closed():
    runner = TemporalWorkflowRunner()
    assert runner.configured is False
    with pytest.raises(TemporalUnavailableError):
        runner.run(None, None)


def test_otel_spans_record_timing_and_service():
    sink = LocalTracer()
    tracer = OtelTracer(sink, service="unbodge-api")
    assert OtelTracer.sdk_available() is False
    with tracer.span("webhook", event="issues"):
        pass
    (event,) = sink.events()
    assert event.name == "otel.webhook"
    assert event.attributes["service"] == "unbodge-api"
    assert float(event.attributes["duration_ms"]) >= 0.0
    assert len(event.attributes["span_id"]) == 16


def test_scrub_redacts_secrets_deterministically():
    dirty = (
        "token sk-live-ABCDEF1234567890 and AKIAIOSFODNN7EXAMPLE "
        "plus password=hunter2 and GITHUB_TOKEN=ghp_deadbeef0123456789"
    )
    first, count = scrub_text(dirty)
    second, _ = scrub_text(dirty)
    assert first == second and count >= 3
    assert "sk-live" not in first and "AKIAIOSFODNN7EXAMPLE" not in first
    assert "hunter2" not in first and "ghp_deadbeef" not in first
    clean, found = scrub_text("nothing sensitive here 12345")
    assert clean == "nothing sensitive here 12345" and found == 0
    assert scrub_text(123) == (123, 0)


@pytest.mark.parametrize(
    "secret",
    [
        "sk-ant-abc123XYZ7890qrs",
        "sk-proj-abc123XYZ7890",
        "sk_live_abc123XYZ7890",
        "ghs_abc123XYZ7890qrs",
        "ghu_abc123XYZ7890qrs",
        "ghr_abc123XYZ7890qrs",
        "ASIAIOSFODNN7EXAMPLE",
        "AIzaSyAbc123XYZ7890qrs12",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
    ],
)
def test_scrub_covers_credential_families(secret):
    cleaned, count = scrub_text(f"leaked {secret} here")
    assert secret not in cleaned and count >= 1


def test_scrub_covers_quoted_and_compound_keys():
    cleaned, count = scrub_text('{"password": "hunter2", "api_key": "zz9"}')
    assert "hunter2" not in cleaned and count >= 2
    cleaned, count = scrub_text("aws_secret_access_key = 'AKIAXXXX'")
    assert "AKIAXXXX" not in cleaned
    cleaned, _ = scrub_text("the token expired yesterday without fanfare")
    assert "expired" in cleaned  # prose without assignment is preserved


def test_scrubbed_evidence_binds_to_raw_hash():
    item = make_evidence(
        id="ev:s", evidence_type=EvidenceType.EXPERIMENT_RESULT,
        source="docker-sandbox", claim="cell A passed",
        experiment_id="run:A",
        payload={
            "command": "c", "stdout": "AKIAIOSFODNN7EXAMPLE", "stderr": "",
            "exit_code": 0, "duration_s": 0.1, "environment": {"X": "1"},
            "git_sha": "a" * 40, "dependency_state": {"d": "v"},
            "status": "PASS",
        },
    )
    scrubbed = scrub_item(item)
    assert isinstance(scrubbed, ScrubbedEvidence)
    assert scrubbed.hash == item.hash  # binding preserved
    assert scrubbed.experiment_id == "run:A"
    assert "AKIAIOSFODNN7EXAMPLE" not in scrubbed.payload["stdout"]
    assert scrubbed.redactions >= 1
    # raw record untouched
    assert "AKIAIOSFODNN7EXAMPLE" in item.payload["stdout"]
