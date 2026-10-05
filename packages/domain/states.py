"""Explicit workflow state machine for UNBODGE Phase 1.

There is intentionally no generic ``set_state``: every transition must pass
through :func:`transition` (or :meth:`WorkflowRun.advance`), which rejects any
edge missing from :data:`VALID_TRANSITIONS` with :class:`InvalidTransitionError`.
"""
from __future__ import annotations

from enum import Enum

from domain.errors import InvalidTransitionError


class WorkflowState(str, Enum):
    DISCOVERED = "DISCOVERED"
    INVESTIGATING = "INVESTIGATING"
    CANDIDATE_FOUND = "CANDIDATE_FOUND"
    CAUSAL_ANALYSIS = "CAUSAL_ANALYSIS"
    REPRODUCTION_PLANNED = "REPRODUCTION_PLANNED"
    HISTORICAL_EXECUTION = "HISTORICAL_EXECUTION"
    COUNTERFACTUAL_EXECUTION = "COUNTERFACTUAL_EXECUTION"
    EVIDENCE_VALIDATION = "EVIDENCE_VALIDATION"
    REGRESSION_TESTING = "REGRESSION_TESTING"
    POLICY_DECISION = "POLICY_DECISION"
    ABSTAINED = "ABSTAINED"
    APPROVED_FOR_PR = "APPROVED_FOR_PR"
    PR_CREATED = "PR_CREATED"


VALID_TRANSITIONS: dict[WorkflowState, frozenset[WorkflowState]] = {
    WorkflowState.DISCOVERED: frozenset({WorkflowState.INVESTIGATING}),
    WorkflowState.INVESTIGATING: frozenset({WorkflowState.CANDIDATE_FOUND}),
    WorkflowState.CANDIDATE_FOUND: frozenset({WorkflowState.CAUSAL_ANALYSIS}),
    WorkflowState.CAUSAL_ANALYSIS: frozenset({WorkflowState.REPRODUCTION_PLANNED}),
    WorkflowState.REPRODUCTION_PLANNED: frozenset({WorkflowState.HISTORICAL_EXECUTION}),
    WorkflowState.HISTORICAL_EXECUTION: frozenset({WorkflowState.COUNTERFACTUAL_EXECUTION}),
    WorkflowState.COUNTERFACTUAL_EXECUTION: frozenset({WorkflowState.EVIDENCE_VALIDATION}),
    WorkflowState.EVIDENCE_VALIDATION: frozenset({WorkflowState.REGRESSION_TESTING}),
    WorkflowState.REGRESSION_TESTING: frozenset({WorkflowState.POLICY_DECISION}),
    WorkflowState.POLICY_DECISION: frozenset(
        {WorkflowState.ABSTAINED, WorkflowState.APPROVED_FOR_PR}
    ),
    WorkflowState.APPROVED_FOR_PR: frozenset({WorkflowState.PR_CREATED}),
    WorkflowState.ABSTAINED: frozenset(),
    WorkflowState.PR_CREATED: frozenset(),
}

TERMINAL_STATES = frozenset({WorkflowState.ABSTAINED, WorkflowState.PR_CREATED})


def can_transition(frm: WorkflowState, to: WorkflowState) -> bool:
    """Return True iff ``frm -> to`` is an explicitly allowed edge."""
    return to in VALID_TRANSITIONS.get(frm, frozenset())


def transition(frm: WorkflowState, to: WorkflowState) -> WorkflowState:
    """Advance ``frm -> to`` or raise :class:`InvalidTransitionError`."""
    if not can_transition(frm, to):
        raise InvalidTransitionError(frm, to)
    return to


def is_terminal(state: WorkflowState) -> bool:
    return state in TERMINAL_STATES