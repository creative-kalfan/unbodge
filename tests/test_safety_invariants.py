"""Phase 3 safety invariants: reasoning proposes, determinism disposes."""

import inspect

import pytest

from domain.enums import DecisionOutcome, PolicyMode, TestStatus, UniverseCell
from domain.models import EvidenceItem, EvidenceType
from evidence.items import make_evidence
from evidence.validation import validate_item
from policy.engine import PolicyInput, evaluate_policy
from reasoning.mock import MockReasoningProvider
from sandbox.base import sanitize_command
from sandbox.docker import DockerSandbox
from sandbox.errors import CommandRejectedError
from support import CANONICAL_MATRIX


def _base(**overrides):
    kwargs = dict(
        mode=PolicyMode.PROPOSE_ONLY,
        evidence_valid=True,
        matrix=dict(CANONICAL_MATRIX),
        regression=TestStatus.PASS,
        evidence_ids=("ev:1",),
        hypothesis_id="hyp:1",
        decision_id="d:1",
    )
    kwargs.update(overrides)
    return PolicyInput(**kwargs)


def test_llm_output_cannot_create_proposal():
    """No text input anywhere on the policy path."""
    import dataclasses

    params = inspect.signature(PolicyInput).parameters
    assert "model_text" not in params and "confidence" not in params
    assert "llm" not in str(params).lower()
    assert "synthesis" not in str(inspect.signature(evaluate_policy)).lower()
    field_names = {f.name for f in dataclasses.fields(PolicyInput)}
    assert field_names == {
        "mode", "evidence_valid", "matrix", "regression",
        "evidence_ids", "hypothesis_id", "decision_id",
    }


def test_confidence_cannot_override_evidence():
    decision = evaluate_policy(_base(evidence_valid=False))
    assert decision.outcome == DecisionOutcome.ABSTAIN
    forged = MockReasoningProvider().synthesize_evidence(
        hypothesis_id="hyp:1", evidence_ids=["ev:1"]
    )
    assert forged.assessment.value == "INSUFFICIENT"
    assert forged.verified is False
    # policy never reads the synthesis: full proof still proposes
    assert evaluate_policy(_base()).outcome == DecisionOutcome.PROPOSE_REMOVAL


def test_research_never_self_certifies():
    item = make_evidence(
        id="ev:r", evidence_type=EvidenceType.SEARCH_RESULT, source="tavily",
        claim="someone wrote something", artifact_ref="https://example.com",
        payload={"query": "q"},
    )
    assert validate_item(item).valid  # format-valid...
    # ...but research alone cannot satisfy the removal bar
    decision = evaluate_policy(_base(matrix={}, evidence_ids=("ev:r",)))
    assert decision.outcome == DecisionOutcome.ABSTAIN


def test_model_commands_cannot_bypass_sandbox(monkeypatch):
    proposal = MockReasoningProvider().generate_reproduction(
        hypothesis_id="h", claim="c"
    )
    assert proposal.commands  # the model MAY propose commands...
    # ...but the execution path has no parameter that could carry them
    from experiments.real import run_real_suite
    from workflow.stages import PipelineContext

    assert "proposal" not in str(inspect.signature(run_real_suite)).lower()
    assert "commands" not in str(inspect.signature(run_real_suite)).lower()
    assert "proposal" not in PipelineContext.__dataclass_fields__
    import sandbox.docker as docker_module

    monkeypatch.setattr(docker_module.shutil, "which", lambda _: "/fake/docker")
    sandbox = DockerSandbox()  # never touches a daemon: validation runs first
    with pytest.raises(CommandRejectedError):
        sandbox.run_container({}, ["rm", "-rf", "/"], {})
    for hostile in (
        "synthetic-check; rm -rf /",
        "synthetic-check --dep OLD --workaround PRESENT && whoami",
    ):
        with pytest.raises(CommandRejectedError):
            sanitize_command(hostile, ("synthetic-check",))
    # ...but execution only happens through validated argv
    assert proposal.verified is False


def test_contradictory_experiments_abstain():
    matrix = dict(CANONICAL_MATRIX)
    matrix[UniverseCell.C] = TestStatus.FAIL
    decision = evaluate_policy(_base(matrix=matrix))
    assert decision.outcome == DecisionOutcome.ABSTAIN


def test_failed_regression_blocks_removal():
    decision = evaluate_policy(_base(regression=TestStatus.FAIL))
    assert decision.outcome == DecisionOutcome.ABSTAIN


def test_missing_evidence_abstains():
    assert evaluate_policy(_base(evidence_valid=False)).outcome == DecisionOutcome.ABSTAIN
    assert evaluate_policy(_base(evidence_ids=())).outcome == DecisionOutcome.ABSTAIN


def test_policy_is_deterministic():
    first = evaluate_policy(_base())
    second = evaluate_policy(_base())
    for decision in (first, second):
        assert decision.outcome == DecisionOutcome.PROPOSE_REMOVAL
    assert first.rationale == second.rationale
    assert first.evidence_ids == second.evidence_ids
    assert first.policy_mode == second.policy_mode
    assert first.id == second.id


def test_evidence_is_immutable():
    from pydantic import ValidationError

    item = make_evidence(
        id="ev:i", evidence_type=EvidenceType.CODE_REFERENCE,
        source="s", claim="c",
    )
    with pytest.raises(ValidationError):
        item.claim = "rewritten"  # type: ignore[misc]


def test_no_auto_merge_path_exists():
    import policy.engine as engine

    merge_capabilities = [name for name in dir(engine) if "merge" in name.lower()]
    assert merge_capabilities == []
    for mode in (PolicyMode.STRICT_AUTO_MERGE, PolicyMode.HUMAN_APPROVAL_REQUIRED):
        decision = evaluate_policy(_base(mode=mode))
        assert decision.outcome == DecisionOutcome.ABSTAIN
