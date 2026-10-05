"""Shared deterministic builders for Phase 1 tests (fixtures only, no logic)."""
from __future__ import annotations

from domain.enums import EvidenceType, TestStatus, UniverseCell
from domain.models import (
    CausalHypothesis,
    ExperimentRun,
    FixCommit,
    Release,
    Repository,
    ReproductionPlan,
    UpstreamIssue,
    WorkaroundCandidate,
    WorkflowRun,
)
from evidence.items import make_evidence
from experiments.planner import NEW_GIT_SHA, OLD_GIT_SHA
from experiments.synthetic import regression_handler, synthetic_handler
from sandbox.base import ResourceLimits, SandboxConstraints
from sandbox.local import LocalDeterministicSandbox

FIX_SHA = "c" * 40


def make_repo() -> Repository:
    return Repository(id="repo:1", full_name="acme/downstream")


def make_issue(repo_id: str = "repo:1") -> UpstreamIssue:
    return UpstreamIssue(
        id="issue:1", repository_id=repo_id, number=42,
        title="nickname lookup crashes on anonymous profiles",
    )


def make_fix(repo_id: str = "repo:1") -> FixCommit:
    return FixCommit(
        id="fix:1", repository_id=repo_id, sha=FIX_SHA,
        message="default missing nicknames to anonymous",
    )


def make_release(repo_id: str = "repo:1") -> Release:
    return Release(
        id="rel:1", repository_id=repo_id, tag="v1.1",
        version="1.1", contains_fix_sha=FIX_SHA,
    )


def make_candidate(repo_id: str = "repo:1") -> WorkaroundCandidate:
    return WorkaroundCandidate(
        id="cand:1", repository_id=repo_id,
        file_path="src/profiles.py", start_line=10, end_line=16,
        description="try/except KeyError fallback to anonymous",
        detector="ExceptionWorkaroundDetector",
    )


def make_hypothesis() -> CausalHypothesis:
    return CausalHypothesis(
        id="hyp:1", candidate_id="cand:1", issue_id="issue:1",
        fix_commit_id="fix:1", release_id="rel:1",
        claim="workaround compensates for the upstream nickname bug fixed in v1.1",
        confidence=0.9,
    )


def make_plan() -> ReproductionPlan:
    return ReproductionPlan(
        id="plan:1", hypothesis_id="hyp:1",
        commands=["synthetic-check --dep OLD --workaround ABSENT"],
    )


def make_workflow() -> WorkflowRun:
    return WorkflowRun(id="wf:1", hypothesis_id="hyp:1")


def make_sandbox(
    limits: ResourceLimits | None = None,
) -> LocalDeterministicSandbox:
    constraints = SandboxConstraints(
        limits=limits or ResourceLimits(),
    )
    return LocalDeterministicSandbox(
        constraints=constraints,
        handlers={
            "synthetic-check": synthetic_handler,
            "regression-suite": regression_handler,
        },
    )


def experiment_payload(run: ExperimentRun) -> dict:
    return {
        "command": run.command,
        "stdout": run.stdout,
        "stderr": run.stderr,
        "exit_code": run.exit_code,
        "duration_s": run.duration_s,
        "environment": dict(run.environment),
        "git_sha": run.git_sha,
        "dependency_state": dict(run.dependency_state),
        "status": run.status.value,
        "test_report": dict(run.test_report),
        "artifact_hashes": dict(run.artifact_hashes),
    }


def experiment_evidence(run: ExperimentRun, index: int = 0):
    return make_evidence(
        id=f"ev:exp:{run.cell.value}:{index}",
        evidence_type=EvidenceType.EXPERIMENT_RESULT,
        source="local-sandbox",
        claim=f"cell {run.cell.value} resulted in {run.status.value}",
        artifact_ref=f"artifact:{run.id}",
        experiment_id=run.id,
        payload=experiment_payload(run),
    )


CANONICAL_MATRIX = {
    UniverseCell.A: TestStatus.PASS,
    UniverseCell.B: TestStatus.FAIL,
    UniverseCell.C: TestStatus.PASS,
    UniverseCell.D: TestStatus.PASS,
}

GIT_BY_CELL = {
    UniverseCell.A: OLD_GIT_SHA,
    UniverseCell.B: OLD_GIT_SHA,
    UniverseCell.C: NEW_GIT_SHA,
    UniverseCell.D: NEW_GIT_SHA,
}