"""Extra contract coverage: models used by the architecture but without
dedicated tests (UpstreamEvent, HumanReview, PullRequestResult, links)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.enums import EvidenceType, ReviewVerdict
from domain.models import (
    EvidenceLink,
    HumanReview,
    PullRequestResult,
    UpstreamEvent,
    WorkflowTransitionRecord,
)
from domain.states import WorkflowState
from evidence.items import make_evidence
from evidence.validation import validate_item
from support import make_candidate, make_fix, make_hypothesis, make_release


def test_upstream_event_defaults_and_validation():
    event = UpstreamEvent(id="evt:1", repository_id="repo:1", title="upstream bug filed")
    assert event.source == "github"
    assert event.body == ""
    with pytest.raises(ValidationError):
        UpstreamEvent(id="e", repository_id="r", title="")


def test_human_review_records_verdict():
    review = HumanReview(
        id="hr:1", decision_id="decision:1", reviewer="alice",
        verdict=ReviewVerdict.APPROVE, comment="proof checked",
    )
    assert review.verdict == ReviewVerdict.APPROVE
    with pytest.raises(ValidationError):
        HumanReview(id="h", decision_id="d", reviewer="", verdict=ReviewVerdict.APPROVE)


def test_pull_request_result_defaults_to_main():
    pr = PullRequestResult(
        id="pr:1", decision_id="decision:1", title="Remove workaround",
        body="evidence...", branch="unbodge/remove-w1",
    )
    assert pr.base == "main"
    with pytest.raises(ValidationError):
        PullRequestResult(
            id="p", decision_id="d", title="", body="b",
            branch="unbodge/x",
        )


def test_evidence_link_defaults_to_supports():
    link = EvidenceLink(from_id="ev:a", to_id="ev:b")
    assert link.relation == "supports"


def test_transition_record_links_states():
    record = WorkflowTransitionRecord(
        from_state=WorkflowState.DISCOVERED, to_state=WorkflowState.INVESTIGATING
    )
    assert record.from_state != record.to_state


def test_candidate_fix_release_chain_links():
    candidate = make_candidate()
    fix = make_fix()
    release = make_release()
    hypothesis = make_hypothesis()
    assert hypothesis.candidate_id == candidate.id
    assert hypothesis.fix_commit_id == fix.id
    assert hypothesis.release_id == release.id
    assert release.contains_fix_sha == fix.sha


def test_search_and_human_review_evidence_validate():
    for evidence_type in (EvidenceType.SEARCH_RESULT, EvidenceType.HUMAN_REVIEW):
        item = make_evidence(
            id=f"ev:{evidence_type.value}", evidence_type=evidence_type,
            source="test", claim="c",
        )
        assert validate_item(item).valid, validate_item(item).errors
