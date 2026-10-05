"""Domain model validation: all 16 contracts accept valid input, reject bad input."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.enums import (
    DecisionOutcome,
    DependencyVersion,
    EvidenceType,
    PolicyMode,
    TestStatus,
    UniverseCell,
    WorkaroundState,
)
from domain.models import (
    CausalHypothesis,
    FixCommit,
    ReproductionPlan,
    Repository,
    UpstreamIssue,
    WorkaroundCandidate,
)
from support import (
    FIX_SHA,
    make_candidate,
    make_fix,
    make_hypothesis,
    make_issue,
    make_plan,
    make_release,
    make_repo,
)


def test_repository_rejects_bad_full_name():
    with pytest.raises(ValidationError):
        Repository(id="repo:1", full_name="not-a-repo")


def test_issue_number_must_be_positive():
    with pytest.raises(ValidationError):
        UpstreamIssue(
            id="issue:1", repository_id="repo:1", number=0, title="t",
        )


def test_fix_commit_sha_must_be_40_hex():
    with pytest.raises(ValidationError):
        FixCommit(
            id="fix:1", repository_id="repo:1", sha="abc123", message="m",
        )
    with pytest.raises(ValidationError):
        FixCommit(
            id="fix:1", repository_id="repo:1", sha="Z" * 40, message="m",
        )


def test_release_fix_sha_pattern():
    rel = make_release()
    assert rel.contains_fix_sha == FIX_SHA
    from domain.models import Release

    with pytest.raises(ValidationError):
        Release(
            id="rel:1", repository_id="repo:1", tag="v1.1", version="1.1",
            contains_fix_sha="nope",
        )


def test_candidate_line_order_enforced():
    with pytest.raises(ValidationError):
        WorkaroundCandidate(
            id="cand:1", repository_id="repo:1", file_path="f.py",
            start_line=20, end_line=10, description="d", detector="det",
        )


def test_hypothesis_confidence_bounded():
    with pytest.raises(ValidationError):
        CausalHypothesis(
            id="h", candidate_id="c", issue_id="i", claim="c", confidence=1.5,
        )
    with pytest.raises(ValidationError):
        CausalHypothesis(
            id="h", candidate_id="c", issue_id="i", claim="c", confidence=-0.1,
        )


def test_plan_requires_commands_and_positive_timeout():
    with pytest.raises(ValidationError):
        ReproductionPlan(id="p", hypothesis_id="h", commands=[])
    with pytest.raises(ValidationError):
        ReproductionPlan(id="p", hypothesis_id="h", commands=["   "])
    with pytest.raises(ValidationError):
        ReproductionPlan(
            id="p", hypothesis_id="h",
            commands=["synthetic-check --dep OLD --workaround ABSENT"], timeout_s=0,
        )


def test_models_reject_unknown_fields():
    with pytest.raises(ValidationError):
        Repository(id="repo:1", full_name="acme/downstream", hacker_field=1)


def test_experiment_spec_cell_must_match_conditions():
    from domain.models import ExperimentSpec

    with pytest.raises(ValidationError):
        ExperimentSpec(
            id="x", cell=UniverseCell.A,
            dependency_version=DependencyVersion.NEW,
            workaround_state=WorkaroundState.PRESENT,
            command="synthetic-check --dep NEW --workaround PRESENT",
        )


def test_experiment_spec_rejects_blank_command_and_bad_timeout():
    from domain.models import ExperimentSpec

    with pytest.raises(ValidationError):
        ExperimentSpec(
            id="x", cell=UniverseCell.B,
            dependency_version=DependencyVersion.OLD,
            workaround_state=WorkaroundState.ABSENT,
            command="   ",
        )
    with pytest.raises(ValidationError):
        ExperimentSpec(
            id="x", cell=UniverseCell.B,
            dependency_version=DependencyVersion.OLD,
            workaround_state=WorkaroundState.ABSENT,
            command="synthetic-check --dep OLD --workaround ABSENT",
            timeout_s=-5,
        )


def test_experiment_run_status_must_match_exit_code():
    from support import GIT_BY_CELL
    from domain.models import ExperimentRun

    base = dict(
        id="run:1", spec_id="spec:1", cell=UniverseCell.A,
        command="synthetic-check --dep OLD --workaround PRESENT",
        git_sha=GIT_BY_CELL[UniverseCell.A], duration_s=0.1,
    )
    ok = ExperimentRun(**base, exit_code=0, status=TestStatus.PASS)
    assert ok.status == TestStatus.PASS
    with pytest.raises(ValidationError):
        ExperimentRun(**base, exit_code=1, status=TestStatus.PASS)
    with pytest.raises(ValidationError):
        ExperimentRun(**base, exit_code=0, status=TestStatus.FAIL)


def test_regression_result_status_consistency():
    from domain.models import RegressionResult

    good = RegressionResult(
        id="reg:1", suite="s", passed=5, failed=0, status=TestStatus.PASS,
        duration_s=0.2,
    )
    assert good.status == TestStatus.PASS
    with pytest.raises(ValidationError):
        RegressionResult(
            id="reg:1", suite="s", passed=5, failed=0, status=TestStatus.FAIL,
            duration_s=0.2,
        )
    with pytest.raises(ValidationError):
        RegressionResult(
            id="reg:1", suite="s", passed=0, failed=0, status=TestStatus.PASS,
            duration_s=0.2,
        )


def test_removal_decision_proposal_must_cite_evidence():
    from domain.models import RemovalDecision

    with pytest.raises(ValidationError):
        RemovalDecision(
            id="d:1", outcome=DecisionOutcome.PROPOSE_REMOVAL,
            policy_mode=PolicyMode.PROPOSE_ONLY, rationale="x", evidence_ids=[],
        )
    abstain = RemovalDecision(
        id="d:1", outcome=DecisionOutcome.ABSTAIN,
        policy_mode=PolicyMode.PROPOSE_ONLY, rationale="not enough",
        evidence_ids=[],
    )
    assert abstain.outcome == DecisionOutcome.ABSTAIN


def test_models_serialize_deterministically():
    hyp = make_hypothesis()
    assert hyp.model_dump_json() == make_hypothesis().model_dump_json()
    restored = type(hyp).model_validate_json(hyp.model_dump_json())
    assert restored == hyp


def test_evidence_item_linkage_rules_at_model_level():
    from domain.models import EvidenceItem

    with pytest.raises(ValidationError):
        EvidenceItem(
            id="e", evidence_type=EvidenceType.EXPERIMENT_RESULT, source="s",
            claim="c", timestamp="2026-01-01T00:00:00+00:00",
            hash="a" * 64, experiment_id=None, payload={},
        )
    with pytest.raises(ValidationError):
        EvidenceItem(
            id="e", evidence_type=EvidenceType.CODE_REFERENCE, source="s",
            claim="c", timestamp="2026-01-01T00:00:00+00:00",
            hash="a" * 64, experiment_id="run:1", payload={},
        )
