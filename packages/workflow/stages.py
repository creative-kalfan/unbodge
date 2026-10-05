"""Typed proof-pipeline stages (Phase 2).

Each stage is a module-level function ``(PipelineState, PipelineContext)
-> PipelineState`` with no framework imports: a Temporal activity can wrap
any stage 1:1 later. The local ``run_pipeline`` executes them in order.
No reasoning, no LLM -- every choice is explicit in the context/state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from tempfile import TemporaryDirectory

from analysis.scanner import scan_tree
from domain.enums import DecisionOutcome, EvidenceType, PolicyMode, TestStatus, UniverseCell
from domain.errors import DomainError
from domain.models import (
    CausalHypothesis,
    EvidenceItem,
    ExperimentRun,
    RegressionResult,
    RemovalDecision,
    ReproductionPlan,
    UpstreamEvent,
    WorkaroundCandidate,
    WorkflowRun,
)
from domain.states import WorkflowState
from evidence.chain import build_proof_graph, run_payload
from evidence.graph import validate_graph
from evidence.items import make_evidence
from evidence.validation import ensure_valid, validate_item
from experiments.real import (
    ensure_workaround_state,
    prepare_cell_workdir,
    read_workdir_files,
    run_real_suite,
)
from experiments.runner import parse_regression_counts
from github.git import GitRepo
from history.reconstruction import Reconstructor
from history.states import HistoryError, HistoricalState
from policy.engine import PolicyInput, evaluate_policy
from pr.generator import LocalPrGenerator, render_pr_body
from pydantic import BaseModel, ConfigDict, Field
from pypi.base import PyPIClient
from sandbox.docker import DockerSandbox

STAGE_NAMES: tuple[str, ...] = (
    "ingest_event",
    "collect_upstream_evidence",
    "identify_release",
    "scan_repository",
    "analyze_candidates",
    "build_causal_hypothesis",
    "plan_reproduction",
    "prepare_environment",
    "run_experiments",
    "collect_evidence",
    "run_regression_tests",
    "validate_policy",
    "create_pr",
)

#: Workflow state entered when the stage completes (None = no transition).
STAGE_STATES: dict[str, WorkflowState | None] = {
    "ingest_event": WorkflowState.INVESTIGATING,
    "collect_upstream_evidence": None,
    "identify_release": None,
    "scan_repository": WorkflowState.CANDIDATE_FOUND,
    "analyze_candidates": WorkflowState.CAUSAL_ANALYSIS,
    "build_causal_hypothesis": None,
    "plan_reproduction": WorkflowState.REPRODUCTION_PLANNED,
    "prepare_environment": WorkflowState.HISTORICAL_EXECUTION,
    "run_experiments": WorkflowState.COUNTERFACTUAL_EXECUTION,
    "collect_evidence": WorkflowState.EVIDENCE_VALIDATION,
    "run_regression_tests": WorkflowState.REGRESSION_TESTING,
    "validate_policy": None,  # stage advances to APPROVED_FOR_PR / ABSTAINED itself
    "create_pr": None,  # stage advances to PR_CREATED itself (or skips on ABSTAIN)
}


@dataclass(frozen=True)
class PipelineContext:
    """All explicit inputs a proof run needs. No inference anywhere."""

    repository_id: str
    repo_path: str
    old_rev: str
    new_rev: str
    workaround_patch: str
    probe_argv: list[str]
    regression_argv: list[str]
    event: UpstreamEvent
    issue_id: str
    fix_id: str
    fix_sha: str
    releases: tuple = ()
    pypi: PyPIClient | None = None
    sandbox: DockerSandbox | None = None
    plan_id: str = "pipeline:1"
    decision_id: str = "decision:pipeline:1"
    probe_env: dict[str, str] = field(default_factory=dict)
    regression_env: dict[str, str] = field(default_factory=dict)
    timeout_s: float = 60
    scan_exclude_prefixes: tuple[str, ...] = ()


class PipelineState(BaseModel):
    """Pipeline scratch state (serializable; stages return updated copies)."""

    model_config = ConfigDict(extra="forbid")

    completed_stages: tuple[str, ...] = ()
    event_id: str | None = None
    upstream_evidence_ids: tuple[str, ...] = ()
    release_id: str | None = None
    candidates: list[WorkaroundCandidate] = Field(default_factory=list)
    candidate_id: str | None = None
    hypothesis: CausalHypothesis | None = None
    plan: ReproductionPlan | None = None
    plan_id: str | None = None
    old_state: HistoricalState | None = None
    new_state: HistoricalState | None = None
    runs: list[ExperimentRun] = Field(default_factory=list)
    matrix: dict[UniverseCell, TestStatus] = Field(default_factory=dict)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    evidence_ids: tuple[str, ...] = ()
    regression: RegressionResult | None = None
    decision: RemovalDecision | None = None
    pr_id: str | None = None
    pr_skipped: bool = False
    workflow: WorkflowRun | None = None


def _sandbox(ctx: PipelineContext) -> DockerSandbox:
    if ctx.sandbox is None:
        raise HistoryError("pipeline requires a sandbox in the context")
    return ctx.sandbox


def stage_ingest_event(state: PipelineState, ctx: PipelineContext) -> PipelineState:
    return state.model_copy(update={"event_id": ctx.event.id})


def stage_collect_upstream_evidence(
    state: PipelineState, ctx: PipelineContext
) -> PipelineState:
    items = [
        ("issue", EvidenceType.UPSTREAM_ISSUE, ctx.issue_id, "upstream issue recorded"),
        ("fix", EvidenceType.FIX_COMMIT, ctx.fix_id, f"upstream fix commit {ctx.fix_sha}"),
    ]
    ids: list[str] = []
    minted: list[EvidenceItem] = []
    for suffix, evidence_type, ref, claim in items:
        item = ensure_valid(
            make_evidence(
                id=f"ev:{ctx.plan_id}:{suffix}",
                evidence_type=evidence_type,
                source="github-adapter",
                claim=claim,
                artifact_ref=ref,
            )
        )
        ids.append(item.id)
        minted.append(item)
    return state.model_copy(
        update={
            "event_id": ctx.event.id,
            "upstream_evidence_ids": tuple(ids),
            "evidence": [*state.evidence, *minted],
        }
    )


def stage_identify_release(state: PipelineState, ctx: PipelineContext) -> PipelineState:
    for release in ctx.releases:
        if release.contains_fix_sha == ctx.fix_sha:
            item = ensure_valid(
                make_evidence(
                    id=f"ev:{ctx.plan_id}:release",
                    evidence_type=EvidenceType.RELEASE,
                    source="github-adapter",
                    claim=f"release {release.tag} contains fix {ctx.fix_sha}",
                    artifact_ref=release.tag,
                )
            )
            return state.model_copy(
                update={
                    "release_id": release.id,
                    "upstream_evidence_ids": (*state.upstream_evidence_ids, item.id),
                    "evidence": [*state.evidence, item],
                }
            )
    raise HistoryError(f"no release contains fix {ctx.fix_sha!r}")


def stage_scan_repository(state: PipelineState, ctx: PipelineContext) -> PipelineState:
    git = GitRepo(ctx.repo_path)
    with TemporaryDirectory(prefix="unbodge-scan-") as tmp:
        tree = git.archive_to(ctx.new_rev, tmp)
        candidates = scan_tree(
            tree, ctx.repository_id, exclude_prefixes=ctx.scan_exclude_prefixes
        )
    return state.model_copy(update={"candidates": candidates})


def stage_analyze_candidates(state: PipelineState, ctx: PipelineContext) -> PipelineState:
    if not state.candidates:
        raise HistoryError("no workaround candidates found")
    preferred = [c for c in state.candidates if c.detector == "ExceptionWorkaroundDetector"]
    chosen = preferred[0] if preferred else state.candidates[0]
    item = ensure_valid(
        make_evidence(
            id=f"ev:{ctx.plan_id}:workaround",
            evidence_type=EvidenceType.CODE_REFERENCE,
            source="ast-scan",
            claim=f"workaround candidate {chosen.id} ({chosen.detector})",
            artifact_ref=f"{chosen.file_path}:{chosen.start_line}-{chosen.end_line}",
        )
    )
    return state.model_copy(
        update={
            "candidate_id": chosen.id,
            "evidence_ids": (*state.evidence_ids, item.id),
            "evidence": [*state.evidence, item],
        }
    )


def stage_build_causal_hypothesis(
    state: PipelineState, ctx: PipelineContext
) -> PipelineState:
    if state.candidate_id is None:
        raise HistoryError("no candidate selected")
    hypothesis = CausalHypothesis(
        id=f"{ctx.plan_id}:hyp",
        candidate_id=state.candidate_id,
        issue_id=ctx.issue_id,
        fix_commit_id=ctx.fix_id,
        release_id=state.release_id,
        claim=(
            f"candidate {state.candidate_id} compensates for the upstream defect "
            f"fixed by {ctx.fix_sha} in release {state.release_id}"
        ),
        confidence=0.0,
    )
    return state.model_copy(update={"hypothesis": hypothesis})


def stage_plan_reproduction(state: PipelineState, ctx: PipelineContext) -> PipelineState:
    if state.hypothesis is None:
        raise HistoryError("no hypothesis built")
    plan = ReproductionPlan(
        id=f"{ctx.plan_id}:repro",
        hypothesis_id=state.hypothesis.id,
        commands=[" ".join(ctx.probe_argv)],
        env=dict(ctx.probe_env),
        timeout_s=max(1, int(ctx.timeout_s)),
    )
    return state.model_copy(update={"plan": plan, "plan_id": ctx.plan_id})


def stage_prepare_environment(
    state: PipelineState, ctx: PipelineContext
) -> PipelineState:
    if ctx.pypi is None:
        raise HistoryError("pipeline requires a package index in the context")
    recon = Reconstructor(GitRepo(ctx.repo_path), ctx.repository_id)
    old_state = recon.state_at(ctx.old_rev)
    new_state = recon.state_at(ctx.new_rev)
    for historical in (old_state, new_state):
        report = recon.check_installable(historical, ctx.pypi)
        if not report.installable:
            raise HistoryError(f"state {historical.id} not reproducible: {report.missing}")
    minted: list[EvidenceItem] = []
    for historical, label in ((old_state, "old"), (new_state, "new")):
        pins = ", ".join(f"{k}=={v}" for k, v in sorted(historical.lock.packages.items()))
        minted.append(
            ensure_valid(
                make_evidence(
                    id=f"ev:{ctx.plan_id}:dep:{label}",
                    evidence_type=EvidenceType.DEPENDENCY_STATE,
                    source="reconstructor",
                    claim=f"{label} state pins {pins or 'nothing'}",
                    artifact_ref="requirements.txt",
                    payload={"lock": dict(historical.lock.packages)},
                )
            )
        )
    return state.model_copy(
        update={
            "old_state": old_state,
            "new_state": new_state,
            "evidence_ids": (*state.evidence_ids, *(m.id for m in minted)),
            "evidence": [*state.evidence, *minted],
        }
    )


def stage_run_experiments(state: PipelineState, ctx: PipelineContext) -> PipelineState:
    result = run_real_suite(
        git=GitRepo(ctx.repo_path),
        repository_id=ctx.repository_id,
        old_rev=ctx.old_rev,
        new_rev=ctx.new_rev,
        workaround_patch=ctx.workaround_patch,
        probe_argv=list(ctx.probe_argv),
        probe_env=dict(ctx.probe_env),
        sandbox=_sandbox(ctx),
        plan_id=ctx.plan_id,
        timeout_s=ctx.timeout_s,
    )
    ordered = [result.runs[cell] for cell in UniverseCell]
    return state.model_copy(update={"runs": ordered, "matrix": dict(result.matrix)})


def stage_collect_evidence(state: PipelineState, ctx: PipelineContext) -> PipelineState:
    if not state.runs:
        raise HistoryError("no experiment runs to collect evidence from")
    ids: list[str] = []
    minted: list[EvidenceItem] = []
    for index, run in enumerate(state.runs):
        item = ensure_valid(
            make_evidence(
                id=f"ev:{ctx.plan_id}:exp:{run.cell.value}:{index}",
                evidence_type=EvidenceType.EXPERIMENT_RESULT,
                source="docker-sandbox",
                claim=f"cell {run.cell.value} resulted in {run.status.value}",
                artifact_ref=f"artifact:{run.id}",
                experiment_id=run.id,
                payload=run_payload(run),
            )
        )
        ids.append(item.id)
        minted.append(item)
    return state.model_copy(
        update={"evidence_ids": (*state.evidence_ids, *ids), "evidence": [*state.evidence, *minted]}
    )


def stage_run_regression_tests(
    state: PipelineState, ctx: PipelineContext
) -> PipelineState:
    git = GitRepo(ctx.repo_path)
    with TemporaryDirectory(prefix="unbodge-reg-") as tmp:
        workdir = prepare_cell_workdir(git, ctx.new_rev, tmp)
        files = read_workdir_files(workdir)
        container = _sandbox(ctx).run_container(
            files, list(ctx.regression_argv), dict(ctx.regression_env),
            timeout_s=ctx.timeout_s,
        )
    passed, failed = parse_regression_counts(container.stdout)
    status = TestStatus.PASS if (failed == 0 and passed > 0) else TestStatus.FAIL
    if (failed == 0 and passed > 0) != (container.exit_code == 0):
        raise DomainError("regression counts contradict container exit code")
    regression = RegressionResult(
        id=f"regression:{ctx.plan_id}:1",
        suite="regression-probes",
        cell=UniverseCell.D,
        passed=passed,
        failed=failed,
        status=status,
        duration_s=max(container.duration_s, 0.0),
        git_sha=git.rev_parse(ctx.new_rev),
    )
    item = ensure_valid(
        make_evidence(
            id=f"ev:{ctx.plan_id}:reg:0",
            evidence_type=EvidenceType.TEST_RESULT,
            source="docker-sandbox",
            claim=f"regression suite {status.value} on NEW without the workaround",
            artifact_ref=f"artifact:{regression.id}",
            experiment_id=regression.id,
            payload={
                "suite": regression.suite,
                "passed": regression.passed,
                "failed": regression.failed,
                "status": regression.status.value,
            },
        )
    )
    return state.model_copy(
        update={
            "regression": regression,
            "evidence_ids": (*state.evidence_ids, item.id),
            "evidence": [*state.evidence, item],
        }
    )


def _with_advance(state: PipelineState, target: WorkflowState) -> PipelineState:
    """Advance the workflow immutably (copy, then transition)."""
    workflow = state.workflow
    if workflow is None:
        return state
    clone = workflow.model_copy(deep=True)
    clone.advance(target)
    return state.model_copy(update={"workflow": clone})


def stage_validate_policy(state: PipelineState, ctx: PipelineContext) -> PipelineState:
    if state.regression is None or state.hypothesis is None:
        raise HistoryError("policy requires regression and hypothesis")
    if not state.evidence:
        raise HistoryError("policy requires collected evidence")
    for item in state.evidence:
        report = validate_item(item)
        if not report.valid:
            raise HistoryError(f"evidence {item.id} invalid: {report.errors}")
    by_id = {item.id: item for item in state.evidence}
    run_ids = {
        run.cell: f"ev:{ctx.plan_id}:exp:{run.cell.value}:{index}"
        for index, run in enumerate(state.runs)
    }
    ordered = [
        f"ev:{ctx.plan_id}:issue",
        f"ev:{ctx.plan_id}:workaround",
        f"ev:{ctx.plan_id}:fix",
        f"ev:{ctx.plan_id}:release",
        f"ev:{ctx.plan_id}:dep:old",
        f"ev:{ctx.plan_id}:dep:new",
        run_ids[UniverseCell.A],
        run_ids[UniverseCell.B],
        run_ids[UniverseCell.C],
        run_ids[UniverseCell.D],
        f"ev:{ctx.plan_id}:reg:0",
    ]
    missing = [item_id for item_id in ordered if item_id not in by_id]
    if missing:
        raise HistoryError(f"proof chain incomplete, missing: {missing}")
    chain = build_proof_graph(
        [by_id[item_id] for item_id in ordered],
        [
            (ordered[0], ordered[1], "compensates"),
            (ordered[1], ordered[2], "fixed-by"),
            (ordered[2], ordered[3], "released-in"),
            (ordered[3], ordered[4], "documents"),
            (ordered[4], ordered[5], "superseded-by"),
            (ordered[4], ordered[6], "executed-as"),
            (ordered[4], ordered[7], "executed-as"),
            (ordered[5], ordered[8], "executed-as"),
            (ordered[5], ordered[9], "executed-as"),
            (ordered[9], ordered[10], "regression-checked-by"),
        ],
    )
    chain_report = validate_graph(chain)
    decision = evaluate_policy(
        PolicyInput(
            mode=PolicyMode.PROPOSE_ONLY,
            evidence_valid=chain_report.valid,
            matrix=dict(state.matrix),
            regression=state.regression.status,
            evidence_ids=(*state.upstream_evidence_ids, *state.evidence_ids),
            hypothesis_id=state.hypothesis.id,
            decision_id=ctx.decision_id,
        )
    )
    updated = state.model_copy(update={"decision": decision})
    updated = _with_advance(updated, WorkflowState.POLICY_DECISION)
    if decision.outcome == DecisionOutcome.PROPOSE_REMOVAL:
        return _with_advance(updated, WorkflowState.APPROVED_FOR_PR)
    return _with_advance(updated, WorkflowState.ABSTAINED)


def stage_create_pr(state: PipelineState, ctx: PipelineContext) -> PipelineState:
    if state.decision is None or state.hypothesis is None:
        raise HistoryError("PR creation requires a policy decision")
    if state.decision.outcome != DecisionOutcome.PROPOSE_REMOVAL:
        return state.model_copy(update={"pr_skipped": True})
    git = GitRepo(ctx.repo_path)
    with TemporaryDirectory(prefix="unbodge-pr-") as tmp:
        workdir = prepare_cell_workdir(git, ctx.new_rev, tmp)
        ensure_workaround_state(workdir, ctx.workaround_patch, present=False)
        files = read_workdir_files(workdir)
    release_tag = next(
        (r.tag for r in ctx.releases if r.id == state.release_id), state.release_id or "unknown"
    )
    candidate_path = next(
        (c.file_path for c in state.candidates if c.id == state.candidate_id), ""
    )
    body = render_pr_body(
        hypothesis_id=state.hypothesis.id,
        matrix=dict(state.matrix),
        regression_suite=state.regression.suite if state.regression else "unknown",
        regression_passed=state.regression.passed if state.regression else 0,
        regression_failed=state.regression.failed if state.regression else 0,
        evidence_ids=(*state.upstream_evidence_ids, *state.evidence_ids),
        fix_sha=ctx.fix_sha,
        release_tag=release_tag,
        removed_files=[candidate_path] if candidate_path else [],
    )
    pr = LocalPrGenerator(git).create_proposal(
        decision=state.decision,
        title=f"Remove obsolete workaround ({state.candidate_id})",
        body=body,
        files=files,
        base_branch="main",
    )
    updated = state.model_copy(update={"pr_id": pr.id})
    return _with_advance(updated, WorkflowState.PR_CREATED)


STAGE_FNS = {
    "ingest_event": stage_ingest_event,
    "collect_upstream_evidence": stage_collect_upstream_evidence,
    "identify_release": stage_identify_release,
    "scan_repository": stage_scan_repository,
    "analyze_candidates": stage_analyze_candidates,
    "build_causal_hypothesis": stage_build_causal_hypothesis,
    "plan_reproduction": stage_plan_reproduction,
    "prepare_environment": stage_prepare_environment,
    "run_experiments": stage_run_experiments,
    "collect_evidence": stage_collect_evidence,
    "run_regression_tests": stage_run_regression_tests,
    "validate_policy": stage_validate_policy,
    "create_pr": stage_create_pr,
}


__all__ = [
    "STAGE_FNS",
    "STAGE_NAMES",
    "STAGE_STATES",
    "PipelineContext",
    "PipelineState",
]
