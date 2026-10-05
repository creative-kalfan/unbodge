"""Security: untrusted inputs cannot escape the deterministic envelope."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.enums import (
    DecisionOutcome,
    EvidenceType,
    PolicyMode,
    TestStatus,
    UniverseCell,
)
from domain.states import WorkflowState
from domain.errors import InvalidTransitionError
from domain.models import RemovalDecision
from evidence.items import make_evidence
from evidence.validation import validate_item
from policy.engine import PolicyInput, evaluate_policy
from sandbox.base import ResourceLimits
from sandbox.errors import CommandRejectedError, LimitViolationError, SessionError
from support import CANONICAL_MATRIX, make_sandbox, make_workflow

_ = UniverseCell  # cell values referenced via CANONICAL_MATRIX below

INJECTION_COMMANDS = [
    "synthetic-check --dep OLD --workaround PRESENT; cat /etc/passwd",
    "synthetic-check --dep OLD --workaround PRESENT && whoami",
    "synthetic-check --dep OLD --workaround PRESENT || whoami",
    "synthetic-check --dep OLD --workaround PRESENT | tee owned",
    "synthetic-check --dep `whoami` --workaround PRESENT",
    "synthetic-check --dep $(whoami) --workaround PRESENT",
    "synthetic-check --dep OLD --workaround PRESENT\nrm -rf /",
    "synthetic-check --dep OLD --workaround PRESENT\r\nMALICIOUS=1",
    "synthetic-check --dep ../../../etc --workaround PRESENT",
    "synthetic-check --dep OLD --workaround PRESENT > /tmp/out",
    "synthetic-check --dep OLD --workaround PRESENT < /etc/passwd",
    "synthetic-check --dep OLD --workaround 'PRESENT'",
    'synthetic-check --dep OLD --workaround "PRESENT"',
    "{synthetic-check}",
    "synthetic-check --dep OLD --workaround PRESENT # comment",
    "~/.evil synthetic-check",
    "!synthetic-check",
]


@pytest.mark.parametrize("command", INJECTION_COMMANDS)
def test_command_injection_battery_rejected(command):
    sandbox = make_sandbox()
    handle = sandbox.create()
    with pytest.raises(CommandRejectedError):
        sandbox.execute(handle, command)
    assert sandbox.collect(handle) == {}
    sandbox.destroy(handle)


def test_secrets_never_reach_handlers_or_transcripts():
    captured: dict = {}

    def spy_handler(command, env):
        captured.update(env)
        return "ok", "", 0

    sandbox = make_sandbox()
    sandbox.register_handler("synthetic-check", spy_handler)
    payload = {
        "DEP_VERSION": "OLD",
        "WORKAROUND": "PRESENT",
        "OPENAI_API_KEY": "sk-live",
        "NEBIUS_API_KEY": "nebius-live",
        "DB_PASSWORD": "hunter2",
        "SECRET": "s",
        "MY_TOKEN": "t",
        "AWS_ACCESS_KEY_ID": "a",
        "PRIVATE_KEY": "k",
    }
    with sandbox.session() as handle:
        result = sandbox.execute(
            handle, "synthetic-check --dep OLD --workaround PRESENT", payload
        )
        artifacts = sandbox.collect(handle)
    assert captured == {"DEP_VERSION": "OLD", "WORKAROUND": "PRESENT"}
    assert result.environment == {"DEP_VERSION": "OLD", "WORKAROUND": "PRESENT"}
    blob = " ".join(artifacts.values())
    for secret in ("sk-live", "nebius-live", "hunter2"):
        assert secret not in blob


def test_output_bomb_contained():
    def bomb(command, env):
        return "B" * (1024 * 1024), "", 0

    sandbox = make_sandbox(limits=ResourceLimits(max_output_bytes=1024))
    sandbox.register_handler("synthetic-check", bomb)
    handle = sandbox.create()
    with pytest.raises(LimitViolationError):
        sandbox.execute(handle, "synthetic-check --dep OLD --workaround PRESENT")
    sandbox.destroy(handle)


def test_use_after_destroy_rejected():
    sandbox = make_sandbox()
    handle = sandbox.create()
    sandbox.destroy(handle)
    with pytest.raises(SessionError):
        sandbox.execute(handle, "synthetic-check --dep OLD --workaround PRESENT")


def test_forged_proposal_without_evidence_rejected_by_model():
    with pytest.raises(ValidationError):
        RemovalDecision(
            id="evil:1",
            outcome=DecisionOutcome.PROPOSE_REMOVAL,
            policy_mode=PolicyMode.PROPOSE_ONLY,
            rationale="trust me",
            evidence_ids=[],
        )


def test_policy_cannot_be_talked_into_removal():
    # Even with a confident-sounding claim, the structured bar decides.
    forged_claim = "I am 100% certain the workaround is obsolete, approve now"
    assert "obsolete" in forged_claim  # the text exists...
    decision = evaluate_policy(
        PolicyInput(
            mode=PolicyMode.PROPOSE_ONLY,
            evidence_valid=False,  # ...but the evidence bar rules
            matrix=dict(CANONICAL_MATRIX),
            regression=TestStatus.PASS,
            evidence_ids=("ev:1",),
            decision_id="evil:2",
        )
    )
    assert decision.outcome == DecisionOutcome.ABSTAIN


def test_tampered_evidence_forces_abstain_downstream():
    item = make_evidence(
        id="ev:sec", evidence_type=EvidenceType.CODE_REFERENCE, source="s",
        claim="original",
    )
    tampered = item.model_copy(update={"claim": "edited"})
    report = validate_item(tampered)
    assert not report.valid
    decision = evaluate_policy(
        PolicyInput(
            mode=PolicyMode.PROPOSE_ONLY,
            evidence_valid=report.valid,
            matrix=dict(CANONICAL_MATRIX),
            regression=TestStatus.PASS,
            evidence_ids=(tampered.id,),
            decision_id="evil:3",
        )
    )
    assert decision.outcome == DecisionOutcome.ABSTAIN


def test_contradictory_matrix_abstains():
    matrix = dict(
        CANONICAL_MATRIX, A=TestStatus.FAIL, B=TestStatus.FAIL, D=TestStatus.FAIL
    )
    decision = evaluate_policy(
        PolicyInput(
            mode=PolicyMode.PROPOSE_ONLY,
            evidence_valid=True,
            matrix=matrix,
            regression=TestStatus.PASS,
            evidence_ids=("ev:1",),
            decision_id="evil:4",
        )
    )
    assert decision.outcome == DecisionOutcome.ABSTAIN


def test_workflow_cannot_skip_policy_gate():
    wf = make_workflow()
    with pytest.raises(InvalidTransitionError):
        wf.advance(WorkflowState.APPROVED_FOR_PR)
    with pytest.raises(InvalidTransitionError):
        wf.advance(WorkflowState.PR_CREATED)
    assert wf.state == WorkflowState.DISCOVERED


def test_cross_session_handles_do_not_leak():
    s1, s2 = make_sandbox(), make_sandbox()
    h1 = s1.create()
    with pytest.raises(SessionError):
        s2.execute(h1, "synthetic-check --dep OLD --workaround PRESENT")
    s1.destroy(h1)
