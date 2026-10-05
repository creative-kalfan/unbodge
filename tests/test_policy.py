"""Policy gate: canonical proof proposes removal; everything else abstains."""
from __future__ import annotations

from domain.enums import (
    DecisionOutcome,
    PolicyMode,
    TestStatus,
    UniverseCell,
)
from policy.engine import PolicyInput, evaluate_policy
from support import CANONICAL_MATRIX


def _base(**overrides) -> PolicyInput:
    kwargs = dict(
        mode=PolicyMode.PROPOSE_ONLY,
        evidence_valid=True,
        matrix=dict(CANONICAL_MATRIX),
        regression=TestStatus.PASS,
        evidence_ids=("ev:exp:A:0", "ev:exp:B:0", "ev:exp:D:0", "ev:reg:0"),
        hypothesis_id="hyp:1",
        decision_id="decision:1",
    )
    kwargs.update(overrides)
    return PolicyInput(**kwargs)


def test_canonical_proof_proposes_removal():
    decision = evaluate_policy(_base())
    assert decision.outcome == DecisionOutcome.PROPOSE_REMOVAL
    assert decision.policy_mode == PolicyMode.PROPOSE_ONLY
    assert decision.evidence_ids
    assert "OK_PROPOSE" in decision.rationale


def test_invalid_evidence_abstains():
    decision = evaluate_policy(_base(evidence_valid=False))
    assert decision.outcome == DecisionOutcome.ABSTAIN
    assert "EVIDENCE_INVALID" in decision.rationale


def test_matrix_mismatch_abstains():
    matrix = dict(CANONICAL_MATRIX, B=TestStatus.PASS)
    decision = evaluate_policy(_base(matrix=matrix))
    assert decision.outcome == DecisionOutcome.ABSTAIN
    assert "MATRIX_MISMATCH" in decision.rationale


def test_contradictory_evidence_abstains():
    matrix = dict(CANONICAL_MATRIX, C=TestStatus.FAIL)
    decision = evaluate_policy(_base(matrix=matrix))
    assert decision.outcome == DecisionOutcome.ABSTAIN
    assert "CONTRADICTORY_EVIDENCE" in decision.rationale


def test_failed_regression_abstains():
    decision = evaluate_policy(_base(regression=TestStatus.FAIL))
    assert decision.outcome == DecisionOutcome.ABSTAIN
    assert "REGRESSION_FAIL" in decision.rationale


def test_missing_evidence_refs_abstains():
    decision = evaluate_policy(_base(evidence_ids=()))
    assert decision.outcome == DecisionOutcome.ABSTAIN
    assert "MISSING_EVIDENCE_REFS" in decision.rationale


def test_non_propose_modes_never_auto_merge_in_phase_1():
    for mode in (PolicyMode.STRICT_AUTO_MERGE, PolicyMode.HUMAN_APPROVAL_REQUIRED):
        decision = evaluate_policy(_base(mode=mode))
        assert decision.outcome == DecisionOutcome.ABSTAIN
        assert "MODE_NOT_ENABLED" in decision.rationale


def test_policy_accepts_no_text_input():
    import inspect

    params = inspect.signature(PolicyInput).parameters
    assert "model_text" not in params
    assert "llm" not in str(params).lower()
    assert "confidence" not in params