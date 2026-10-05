"""Evidence validation, hashing, immutability, and graph checks."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from domain.enums import EvidenceType, UniverseCell
from domain.models import EvidenceGraph, EvidenceItem, EvidenceLink
from evidence.errors import InvalidEvidenceError
from evidence.graph import validate_graph
from evidence.hashing import evidence_content_hash, sha256_hex
from evidence.items import make_evidence
from evidence.validation import ensure_valid, validate_item
from experiments.planner import plan_counterfactual
from experiments.runner import execute_spec
from support import experiment_evidence, experiment_payload, make_sandbox


def _code_ref(seed: str = "ev:1"):
    return make_evidence(
        id=seed,
        evidence_type=EvidenceType.CODE_REFERENCE,
        source="ast-scan",
        claim="try/except fallback guards nickname lookup",
        artifact_ref="src/profiles.py:10-16",
    )


def test_make_evidence_hash_is_deterministic_for_fixed_timestamp():
    ts = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    kwargs = dict(
        id="ev:x", evidence_type=EvidenceType.CODE_REFERENCE, source="s",
        claim="c", timestamp=ts,
    )
    assert make_evidence(**kwargs).hash == make_evidence(**kwargs).hash


def test_valid_evidence_passes_validation():
    report = validate_item(_code_ref())
    assert report.valid and report.errors == ()


def test_ensure_valid_returns_item():
    item = _code_ref()
    assert ensure_valid(item) is item


def test_malformed_hash_rejected_at_model_level():
    with pytest.raises(ValidationError):
        EvidenceItem(
            id="e", evidence_type=EvidenceType.CODE_REFERENCE, source="s",
            claim="c", timestamp=datetime.now(timezone.utc),
            hash="not-a-hash", payload={},
        )


def test_tampered_content_detected_by_hash_mismatch():
    item = _code_ref()
    tampered = item.model_copy(update={"claim": "edited by an attacker"})
    report = validate_item(tampered)
    assert not report.valid
    assert any("hash mismatch" in err for err in report.errors)
    with pytest.raises(InvalidEvidenceError):
        ensure_valid(tampered)


def test_experiment_evidence_requires_linkage_and_metadata():
    run = execute_spec(
        sandbox=make_sandbox(),
        spec=plan_counterfactual("t:1").specs[UniverseCell.A],
    )
    item = experiment_evidence(run)
    assert validate_item(item).valid

    thin = make_evidence(
        id="ev:thin", evidence_type=EvidenceType.EXPERIMENT_RESULT, source="s",
        claim="c", experiment_id=run.id, payload={"command": "x"},
    )
    report = validate_item(thin)
    assert not report.valid
    assert any("execution metadata" in err for err in report.errors)


def test_inconsistent_experiment_result_rejected():
    run = execute_spec(
        sandbox=make_sandbox(),
        spec=plan_counterfactual("t:2").specs[UniverseCell.B],
    )
    assert run.status.value == "FAIL"

    payload = experiment_payload(run)
    payload["status"] = "PASS"  # lie about the outcome
    forged = make_evidence(
        id="ev:forged", evidence_type=EvidenceType.EXPERIMENT_RESULT, source="s",
        claim="forged pass", experiment_id=run.id, payload=payload,
    )
    report = validate_item(forged)
    assert not report.valid
    assert any("contradicts exit_code" in err for err in report.errors)


def test_test_result_metadata_consistency():
    good = make_evidence(
        id="ev:t", evidence_type=EvidenceType.TEST_RESULT, source="regression",
        claim="suite passed", experiment_id="regression:1",
        payload={"suite": "s", "passed": 5, "failed": 0, "status": "PASS"},
    )
    assert validate_item(good).valid
    bad = make_evidence(
        id="ev:t2", evidence_type=EvidenceType.TEST_RESULT, source="regression",
        claim="suite passed", experiment_id="regression:1",
        payload={"suite": "s", "passed": 5, "failed": 2, "status": "PASS"},
    )
    assert not validate_item(bad).valid


def test_evidence_is_immutable():
    item = _code_ref()
    with pytest.raises(ValidationError):
        item.claim = "mutation attempt"  # type: ignore[misc]


def test_naive_and_future_timestamps_rejected():
    naive = _code_ref("ev:naive").model_copy(
        update={"timestamp": datetime(2026, 1, 1, 12, 0, 0)}
    )
    assert any("timezone" in e for e in validate_item(naive).errors)
    future = _code_ref("ev:future").model_copy(
        update={"timestamp": datetime.now(timezone.utc) + timedelta(days=3)}
    )
    assert any("future" in e for e in validate_item(future).errors)


def test_graph_rejects_dangling_links_duplicates_and_cycles():
    a = _code_ref("ev:a")
    b = _code_ref("ev:b")
    ok_graph = EvidenceGraph(
        items=[a, b],
        links=[EvidenceLink(from_id="ev:a", to_id="ev:b", relation="supports")],
    )
    assert validate_graph(ok_graph).valid

    dangling = EvidenceGraph(
        items=[a], links=[EvidenceLink(from_id="ev:a", to_id="ev:ghost")]
    )
    assert not validate_graph(dangling).valid

    cyclic = EvidenceGraph(
        items=[a, b],
        links=[
            EvidenceLink(from_id="ev:a", to_id="ev:b"),
            EvidenceLink(from_id="ev:b", to_id="ev:a"),
        ],
    )
    report = validate_graph(cyclic)
    assert not report.valid and any("cycle" in e for e in report.errors)

    with pytest.raises(ValidationError):
        EvidenceGraph(items=[a, a], links=[])


def test_hash_helpers_stable():
    assert sha256_hex("abc") == sha256_hex(b"abc")
    assert len(sha256_hex("abc")) == 64
    h1 = evidence_content_hash(
        evidence_type="X", source="s", claim="c", artifact_ref=None,
        timestamp_iso="2026-01-01T00:00:00+00:00", experiment_id=None, payload={},
    )
    assert h1 == evidence_content_hash(
        evidence_type="X", source="s", claim="c", artifact_ref=None,
        timestamp_iso="2026-01-01T00:00:00+00:00", experiment_id=None, payload={},
    )