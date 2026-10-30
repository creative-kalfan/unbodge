"""Local pipeline execution (Phase 2).

Runs the typed stages in order, advancing the ``WorkflowRun`` history.
Completed stages are skipped on re-entry, making runs idempotent where
practical. No orchestration framework: Temporal can wrap ``STAGE_FNS``
entries as activities later without changing stage code.
"""

from __future__ import annotations

from domain.errors import InvalidTransitionError, UnbodgeError
from domain.enums import DecisionOutcome, PolicyMode
from domain.models import RemovalDecision
from domain.states import can_transition
from workflow.stages import (
    STAGE_FNS,
    STAGE_NAMES,
    STAGE_STATES,
    PipelineContext,
    PipelineState,
    _with_advance,
)


def run_pipeline(
    state: PipelineState,
    ctx: PipelineContext,
    *,
    stages: tuple[str, ...] = STAGE_NAMES,
) -> PipelineState:
    """Execute pending stages in order; return the updated state."""
    unknown = [name for name in stages if name not in STAGE_FNS]
    if unknown:
        raise ValueError(f"unknown pipeline stages: {unknown}")
    current = state
    if current.failure:
        return current
    for name in stages:
        if name in current.completed_stages:
            continue
        try:
            current = STAGE_FNS[name](current, ctx)
        except UnbodgeError as exc:
            # Keep the last legal workflow position; do not fabricate completed
            # stages to jump to ABSTAINED. The failure field is explicit and
            # terminal for this run; a new investigation needs fresh proof.
            return current.model_copy(update={
                "failure": str(exc), "pr_skipped": True, "pr_id": None,
                "decision": RemovalDecision(
                    id=ctx.decision_id, hypothesis_id=current.hypothesis.id if current.hypothesis else None,
                    outcome=DecisionOutcome.ABSTAIN, policy_mode=PolicyMode.PROPOSE_ONLY,
                    rationale=f"PROOF_UNAVAILABLE: {exc}",
                    evidence_ids=[e.id for e in current.evidence],
                ),
            })
        target = STAGE_STATES[name]
        workflow = current.workflow
        if target is not None and workflow is not None and workflow.state != target:
            if not can_transition(workflow.state, target):
                raise InvalidTransitionError(workflow.state, target)
            current = _with_advance(current, target)
        current = current.model_copy(
            update={"completed_stages": (*current.completed_stages, name)}
        )
    return current


__all__ = ["run_pipeline"]
