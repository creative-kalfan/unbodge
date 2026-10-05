"""Deterministic policy evaluator (Phase 1).

The gate consumes ONLY structured inputs: evidence validity, the
counterfactual matrix, and the regression result. There is deliberately no
parameter for model-generated text, so prose can never override the gate.

MVP mode is PROPOSE_ONLY. The other modes parse and validate, but Phase 1
never auto-merges: a fully proven case under a non-PROPOSE_ONLY mode still
returns ABSTAIN with MODE_NOT_ENABLED (approval workflows arrive in Phase 2+).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from domain.enums import (
    DecisionOutcome,
    PolicyMode,
    RationaleCode,
    TestStatus,
    UniverseCell,
)
from domain.models import RemovalDecision, utcnow
from experiments.contracts import meets_removal_bar


@dataclass(frozen=True)
class PolicyInput:
    mode: PolicyMode = PolicyMode.PROPOSE_ONLY
    evidence_valid: bool = False
    matrix: Mapping[UniverseCell, TestStatus] = field(default_factory=dict)
    regression: TestStatus = TestStatus.FAIL
    evidence_ids: tuple[str, ...] = ()
    hypothesis_id: str | None = None
    decision_id: str = "decision:1"


def evaluate_policy(policy_input: PolicyInput) -> RemovalDecision:
    rationale: RationaleCode
    outcome: DecisionOutcome

    if not policy_input.evidence_valid:
        outcome, rationale = DecisionOutcome.ABSTAIN, RationaleCode.EVIDENCE_INVALID
    elif not meets_removal_bar(dict(policy_input.matrix)):
        outcome, rationale = _matrix_rationale(policy_input.matrix)
    elif policy_input.regression != TestStatus.PASS:
        outcome, rationale = DecisionOutcome.ABSTAIN, RationaleCode.REGRESSION_FAIL
    elif not policy_input.evidence_ids:
        outcome, rationale = DecisionOutcome.ABSTAIN, RationaleCode.MISSING_EVIDENCE_REFS
    elif policy_input.mode != PolicyMode.PROPOSE_ONLY:
        outcome, rationale = DecisionOutcome.ABSTAIN, RationaleCode.MODE_NOT_ENABLED
    else:
        outcome, rationale = DecisionOutcome.PROPOSE_REMOVAL, RationaleCode.OK_PROPOSE

    return RemovalDecision(
        id=policy_input.decision_id,
        hypothesis_id=policy_input.hypothesis_id,
        outcome=outcome,
        policy_mode=policy_input.mode,
        rationale=f"{rationale.value}: " + _rationale_detail(rationale, policy_input),
        evidence_ids=list(policy_input.evidence_ids),
        created_at=utcnow(),
    )


def _matrix_rationale(
    matrix: Mapping[UniverseCell, TestStatus],
) -> tuple[DecisionOutcome, RationaleCode]:
    if matrix.get(UniverseCell.C) == TestStatus.FAIL and (
        matrix.get(UniverseCell.A) == TestStatus.PASS
        or matrix.get(UniverseCell.D) == TestStatus.PASS
    ):
        return DecisionOutcome.ABSTAIN, RationaleCode.CONTRADICTORY_EVIDENCE
    return DecisionOutcome.ABSTAIN, RationaleCode.MATRIX_MISMATCH


def _rationale_detail(rationale: RationaleCode, policy_input: PolicyInput) -> str:
    def _cell_str(cell: UniverseCell) -> str:
        status = policy_input.matrix.get(cell)
        rendered = status.value if isinstance(status, TestStatus) else "?"
        return f"{cell.value}={rendered}"

    matrix_str = ",".join(
        _cell_str(cell) for cell in UniverseCell if cell in policy_input.matrix
    )
    details = {
        RationaleCode.OK_PROPOSE: (
            f"canonical counterfactual proven [{matrix_str}], "
            f"regression {policy_input.regression.value}, "
            f"evidence refs={len(policy_input.evidence_ids)}"
        ),
        RationaleCode.EVIDENCE_INVALID: "evidence failed deterministic validation",
        RationaleCode.MATRIX_MISMATCH: (
            f"counterfactual matrix does not meet removal bar [{matrix_str}]"
        ),
        RationaleCode.CONTRADICTORY_EVIDENCE: (
            f"contradictory outcomes across universe cells [{matrix_str}]"
        ),
        RationaleCode.REGRESSION_FAIL: (
            f"regression status is {policy_input.regression.value}"
        ),
        RationaleCode.MODE_NOT_ENABLED: (
            f"mode {policy_input.mode.value} has no approval workflow in Phase 1"
        ),
        RationaleCode.MISSING_EVIDENCE_REFS: (
            "PROPOSE_REMOVAL requires cited evidence ids"
        ),
    }
    return details[rationale]