"""Mandatory first green test: the full causal proof path end to end.

The result must EMERGE from the pipeline, never be faked:

  domain contracts -> experiment spec -> sandbox execution -> runs
  -> evidence -> evidence validation -> regression -> policy decision

Canonical assertions:
  OLD + workaround    -> PASS
  OLD + no workaround  -> FAIL
  NEW + no workaround  -> PASS
  regression tests     -> PASS
  evidence             -> VALID
  decision             -> PROPOSE_REMOVAL
"""
from __future__ import annotations

from domain.enums import (
    DecisionOutcome,
    DependencyVersion,
    EvidenceType,
    PolicyMode,
    TestStatus,
    UniverseCell,
)
from domain.states import WorkflowState
from domain.models import EvidenceGraph, EvidenceLink, PullRequestResult
from evidence.graph import validate_graph
from evidence.items import make_evidence
from evidence.validation import EXPERIMENT_METADATA_KEYS, ensure_valid
from experiments.planner import GIT_SHAS, plan_counterfactual
from experiments.runner import run_regression, run_suite
from policy.engine import PolicyInput, evaluate_policy
from support import (
    CANONICAL_MATRIX,
    experiment_evidence,
    experiment_payload,
    make_candidate,
    make_fix,
    make_hypothesis,
    make_issue,
    make_plan,
    make_release,
    make_repo,
    make_sandbox,
    make_workflow,
)


def test_canonical_counterfactual_proof_end_to_end():
    # -- 1. domain contracts: upstream history + downstream hypothesis -------
    repo = make_repo()
    issue = make_issue(repo.id)
    fix = make_fix(repo.id)
    release = make_release(repo.id)
    assert release.contains_fix_sha == fix.sha
    candidate = make_candidate(repo.id)
    hypothesis = make_hypothesis()
    plan = make_plan()
    assert plan.hypothesis_id == hypothesis.id
    assert candidate.id == hypothesis.candidate_id
    assert issue.id == hypothesis.issue_id

    # -- 2. workflow reaches counterfactual execution ------------------------
    wf = make_workflow()
    for nxt in (
        WorkflowState.INVESTIGATING,
        WorkflowState.CANDIDATE_FOUND,
        WorkflowState.CAUSAL_ANALYSIS,
        WorkflowState.REPRODUCTION_PLANNED,
        WorkflowState.HISTORICAL_EXECUTION,
        WorkflowState.COUNTERFACTUAL_EXECUTION,
    ):
        wf.advance(nxt)

    # -- 3. counterfactual plan -> sandbox execution --------------------------
    sandbox = make_sandbox()
    suite = plan_counterfactual(plan.id)
    result = run_suite(sandbox=sandbox, suite=suite)
    matrix = result.matrix

    assert matrix[UniverseCell.A] == TestStatus.PASS, "OLD + workaround -> PASS"
    assert matrix[UniverseCell.B] == TestStatus.FAIL, "OLD + no workaround -> FAIL"
    assert matrix[UniverseCell.C] == TestStatus.PASS, "NEW + workaround -> PASS"
    assert matrix[UniverseCell.D] == TestStatus.PASS, "NEW + no workaround -> PASS"

    # -- 4. evidence creation + deterministic validation -----------------------
    wf.advance(WorkflowState.EVIDENCE_VALIDATION)
    evidence_items = [ensure_valid(experiment_evidence(run)) for run in result.runs.values()]
    assert len(evidence_items) == 4

    graph = EvidenceGraph(
        items=evidence_items,
        links=[
            EvidenceLink(from_id=evidence_items[1].id, to_id=evidence_items[0].id),
            EvidenceLink(from_id=evidence_items[3].id, to_id=evidence_items[0].id),
        ],
    )
    graph_report = validate_graph(graph)
    assert graph_report.valid, graph_report.errors
    evidence_valid = True

    # -- 5. regression on the post-removal state -------------------------------
    wf.advance(WorkflowState.REGRESSION_TESTING)
    regression = run_regression(
        sandbox=sandbox,
        suite="fake-dep-probes",
        command="regression-suite --dep NEW --workaround ABSENT",
        env={"DEP_VERSION": "NEW", "WORKAROUND": "ABSENT"},
        cell=UniverseCell.D,
        run_id="regression:proof:1",
        git_sha=GIT_SHAS[DependencyVersion.NEW],
    )
    assert regression.status == TestStatus.PASS, "regression tests -> PASS"
    regression_evidence = ensure_valid(
        make_evidence(
            id="ev:reg:proof:1",
            evidence_type=EvidenceType.TEST_RESULT,
            source="local-sandbox",
            claim="regression suite passes on NEW without the workaround",
            artifact_ref="artifact:regression:proof:1",
            experiment_id=regression.id,
            payload={
                "suite": regression.suite,
                "passed": regression.passed,
                "failed": regression.failed,
                "status": regression.status.value,
            },
        )
    )
    assert regression_evidence is not None

    # -- 6. deterministic policy decision ---------------------------------------
    wf.advance(WorkflowState.POLICY_DECISION)
    evidence_ids = tuple(item.id for item in evidence_items) + (regression_evidence.id,)
    decision = evaluate_policy(
        PolicyInput(
            mode=PolicyMode.PROPOSE_ONLY,
            evidence_valid=evidence_valid,
            matrix=matrix,
            regression=regression.status,
            evidence_ids=evidence_ids,
            hypothesis_id=hypothesis.id,
            decision_id="decision:proof:1",
        )
    )
    assert decision.outcome == DecisionOutcome.PROPOSE_REMOVAL, "decision -> PROPOSE_REMOVAL"

    # -- 7. approval + PR artifact (rendered from structured evidence) -----------
    wf.advance(WorkflowState.APPROVED_FOR_PR)
    pr = PullRequestResult(
        id="pr:proof:1",
        decision_id=decision.id,
        title="Remove obsolete nickname workaround (proven by counterfactual)",
        body=(
            f"Evidence: {', '.join(evidence_ids)}\n"
            f"Matrix: A={matrix[UniverseCell.A].value} "
            f"B={matrix[UniverseCell.B].value} "
            f"C={matrix[UniverseCell.C].value} "
            f"D={matrix[UniverseCell.D].value}\n"
            f"Regression: {regression.suite} "
            f"passed={regression.passed} failed={regression.failed}\n"
            f"Fix: {fix.sha} released as {release.tag}"
        ),
        branch="unbodge/remove-nickname-workaround",
        base=repo.default_branch,
    )
    wf.advance(WorkflowState.PR_CREATED)
    assert wf.state == WorkflowState.PR_CREATED
    assert pr.decision_id == decision.id


def test_insufficient_evidence_abstains_no_pr():
    # Same pipeline, but the bug does NOT reproduce without the workaround
    # (B unexpectedly PASSes): the gate must ABSTAIN and no PR may follow.
    wf = make_workflow()
    for nxt in (
        WorkflowState.INVESTIGATING,
        WorkflowState.CANDIDATE_FOUND,
        WorkflowState.CAUSAL_ANALYSIS,
        WorkflowState.REPRODUCTION_PLANNED,
        WorkflowState.HISTORICAL_EXECUTION,
        WorkflowState.COUNTERFACTUAL_EXECUTION,
        WorkflowState.EVIDENCE_VALIDATION,
        WorkflowState.REGRESSION_TESTING,
        WorkflowState.POLICY_DECISION,
    ):
        wf.advance(nxt)

    weak_matrix = dict(CANONICAL_MATRIX, B=TestStatus.PASS)
    decision = evaluate_policy(
        PolicyInput(
            mode=PolicyMode.PROPOSE_ONLY,
            evidence_valid=True,
            matrix=weak_matrix,
            regression=TestStatus.PASS,
            evidence_ids=("ev:whatever",),
            hypothesis_id="hyp:1",
            decision_id="decision:weak:1",
        )
    )
    assert decision.outcome == DecisionOutcome.ABSTAIN
    wf.advance(WorkflowState.ABSTAINED)
    assert wf.state == WorkflowState.ABSTAINED


def test_experiment_payload_helper_covers_required_metadata():
    sandbox = make_sandbox()
    run = run_suite(
        sandbox=sandbox, suite=plan_counterfactual("meta:1")
    ).runs[UniverseCell.D]
    payload = experiment_payload(run)
    for key in EXPERIMENT_METADATA_KEYS:
        assert key in payload
