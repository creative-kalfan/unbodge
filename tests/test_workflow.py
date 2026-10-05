"""Workflow state machine: valid chain passes, anything else raises."""
from __future__ import annotations

import pytest

from domain.enums import DecisionOutcome
from domain.errors import InvalidTransitionError
from domain.states import VALID_TRANSITIONS, WorkflowState, can_transition, transition
from support import make_workflow

FULL_PATH = [
    WorkflowState.INVESTIGATING,
    WorkflowState.CANDIDATE_FOUND,
    WorkflowState.CAUSAL_ANALYSIS,
    WorkflowState.REPRODUCTION_PLANNED,
    WorkflowState.HISTORICAL_EXECUTION,
    WorkflowState.COUNTERFACTUAL_EXECUTION,
    WorkflowState.EVIDENCE_VALIDATION,
    WorkflowState.REGRESSION_TESTING,
    WorkflowState.POLICY_DECISION,
    WorkflowState.APPROVED_FOR_PR,
    WorkflowState.PR_CREATED,
]


def test_full_happy_path_transitions():
    wf = make_workflow()
    assert wf.state == WorkflowState.DISCOVERED
    for nxt in FULL_PATH:
        wf.advance(nxt)
    assert wf.state == WorkflowState.PR_CREATED
    assert len(wf.history) == len(FULL_PATH)
    assert wf.history[0].from_state == WorkflowState.DISCOVERED
    assert wf.history[-1].to_state == WorkflowState.PR_CREATED


def test_policy_may_abstain():
    wf = make_workflow()
    for nxt in FULL_PATH[:9]:
        wf.advance(nxt)
    assert wf.state == WorkflowState.POLICY_DECISION
    wf.advance(WorkflowState.ABSTAINED)
    assert wf.state == WorkflowState.ABSTAINED


def test_transition_function_returns_target():
    assert transition(WorkflowState.DISCOVERED, WorkflowState.INVESTIGATING) == (
        WorkflowState.INVESTIGATING
    )


@pytest.mark.parametrize(
    "frm,to",
    [
        (WorkflowState.DISCOVERED, WorkflowState.CANDIDATE_FOUND),
        (WorkflowState.DISCOVERED, WorkflowState.DISCOVERED),
        (WorkflowState.DISCOVERED, WorkflowState.PR_CREATED),
        (WorkflowState.INVESTIGATING, WorkflowState.DISCOVERED),
        (WorkflowState.POLICY_DECISION, WorkflowState.PR_CREATED),
        (WorkflowState.ABSTAINED, WorkflowState.INVESTIGATING),
        (WorkflowState.PR_CREATED, WorkflowState.DISCOVERED),
        (WorkflowState.APPROVED_FOR_PR, WorkflowState.ABSTAINED),
        (WorkflowState.REGRESSION_TESTING, WorkflowState.APPROVED_FOR_PR),
    ],
)
def test_invalid_transitions_raise_typed_error(frm, to):
    assert not can_transition(frm, to)
    with pytest.raises(InvalidTransitionError) as exc:
        transition(frm, to)
    assert exc.value.from_state == frm
    assert exc.value.to_state == to


def test_workflow_run_advance_rejects_and_preserves_state():
    wf = make_workflow()
    with pytest.raises(InvalidTransitionError):
        wf.advance(WorkflowState.PR_CREATED)
    assert wf.state == WorkflowState.DISCOVERED
    assert wf.history == []


def test_every_state_has_explicit_table_entry():
    assert set(VALID_TRANSITIONS.keys()) == set(WorkflowState)
    assert VALID_TRANSITIONS[WorkflowState.ABSTAINED] == frozenset()
    assert VALID_TRANSITIONS[WorkflowState.PR_CREATED] == frozenset()


def test_abstain_path_matches_policy_outcome():
    wf = make_workflow()
    for nxt in FULL_PATH[:9]:
        wf.advance(nxt)
    outcome = DecisionOutcome.ABSTAIN
    wf.advance(
        WorkflowState.ABSTAINED
        if outcome == DecisionOutcome.ABSTAIN
        else WorkflowState.APPROVED_FOR_PR
    )
    assert wf.state == WorkflowState.ABSTAINED