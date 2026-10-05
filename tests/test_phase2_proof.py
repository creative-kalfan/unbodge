"""Phase 2 end-to-end: real history -> detection -> counterfactual proof.

Canonical case: OLD+workaround PASS, OLD-workaround FAIL, NEW +/- PASS,
regression PASS, evidence VALID, decision PROPOSE_REMOVAL, PR created.
Ambiguous case (no reproducible bug): ABSTAIN, no PR.
"""

import pytest

from domain.enums import DecisionOutcome, EvidenceType, TestStatus, UniverseCell
from domain.models import Release, UpstreamEvent, WorkflowRun
from evidence.chain import build_chain_graph, check_chain
from evidence.items import make_evidence
from evidence.validation import validate_item
from phase2_support import (
    UPSTREAM_FIX_SHA,
    WORKAROUND_PATCH,
    build_downstream_fixture,
)
from policy.engine import PolicyMode
from pypi.base import FixturePyPIClient, ReleaseMetadata
from sandbox.docker import DockerSandbox, docker_available
from support import CANONICAL_MATRIX
from workflow.pipeline import run_pipeline
from workflow.stages import PipelineContext, PipelineState

needs_docker = pytest.mark.skipif(
    not docker_available(), reason="docker daemon or image unavailable"
)

REPO_ID = "repo:downstream"


def _pypi():
    return FixturePyPIClient(
        {
            "fake-dep": {
                "1.0": ReleaseMetadata(name="fake-dep", version="1.0"),
                "1.1": ReleaseMetadata(name="fake-dep", version="1.1"),
            }
        }
    )


def _releases():
    return (
        Release(
            id="rel:0", repository_id=REPO_ID, tag="v1.0", version="1.0",
            contains_fix_sha="0" * 40,
        ),
        Release(
            id="rel:1", repository_id=REPO_ID, tag="v1.1", version="1.1",
            contains_fix_sha=UPSTREAM_FIX_SHA,
        ),
    )


def _context(refs, releases) -> PipelineContext:
    return PipelineContext(
        repository_id=REPO_ID,
        repo_path=str(refs["root"]),
        old_rev=refs["old_tag"],
        new_rev=refs["new_tag"],
        workaround_patch=refs["patch"],
        probe_argv=["python", "probe.py"],
        regression_argv=["python", "regression_probe.py"],
        event=UpstreamEvent(
            id="evt:7", repository_id=REPO_ID,
            title="nickname lookup crashes on anonymous profiles",
        ),
        issue_id="issue:7",
        fix_id="fix:1",
        fix_sha=UPSTREAM_FIX_SHA,
        releases=releases,
        pypi=_pypi(),
        sandbox=DockerSandbox(),
        plan_id="phase2:proof",
        decision_id="decision:phase2:proof",
        probe_env={"DEP_VERSION": "OLD", "WORKAROUND": "PRESENT"},
        regression_env={"DEP_VERSION": "NEW", "WORKAROUND": "ABSENT"},
    )


@needs_docker
def test_phase2_local_proof_end_to_end(tmp_path):
    refs = build_downstream_fixture(tmp_path / "downstream")
    ctx = _context(refs, _releases())
    initial = PipelineState(workflow=WorkflowRun(id="wf:phase2", hypothesis_id=None))
    final = run_pipeline(initial, ctx)

    assert final.matrix == dict(CANONICAL_MATRIX)
    assert final.regression is not None and final.regression.status == TestStatus.PASS
    assert final.decision is not None
    assert final.decision.outcome == DecisionOutcome.PROPOSE_REMOVAL
    assert final.decision.policy_mode == PolicyMode.PROPOSE_ONLY
    assert final.pr_id is not None and not final.pr_skipped
    assert final.workflow is not None and final.workflow.state.value == "PR_CREATED"

    # evidence: every item validates; the explicit chain graph validates
    # issue + fix, release, workaround-ref, 2 dep states, 4 experiments, regression
    assert len(final.evidence) == 2 + 1 + 1 + 2 + 4 + 1
    for item in final.evidence:
        assert validate_item(item).valid, validate_item(item).errors
    by_id = {item.id for item in final.evidence}
    assert f"ev:phase2:proof:release" in by_id
    assert f"ev:phase2:proof:workaround" in by_id
    assert f"ev:phase2:proof:dep:old" in by_id
    assert f"ev:phase2:proof:dep:new" in by_id
    assert check_chain(build_chain_graph(final.evidence)).valid
    assert set(final.decision.evidence_ids) == by_id

    # causal links are explicit
    assert final.hypothesis is not None
    assert final.hypothesis.candidate_id == final.candidate_id
    assert final.old_state.lock.version_of("fake-dep") == "1.0"
    assert final.new_state.lock.version_of("fake-dep") == "1.1"

    # idempotent re-entry: nothing re-runs
    again = run_pipeline(final, ctx)
    assert again.completed_stages == final.completed_stages
    assert again.decision.id == final.decision.id


@needs_docker
def test_phase2_ambiguous_case_abstains_without_pr(tmp_path):
    # No reproducible bug: the OLD state is already fixed, so cell B passes
    # and the removal bar cannot be met -- but a workaround IS present, so
    # the pipeline reaches policy and must ABSTAIN (no PR).
    from phase2_support import (
        APP_PATCHED,
        APP_PLAIN,
        DEP_NEW,
        PROBE_PY,
        REGRESSION_PY,
        WORKAROUND_PY,
        commit_all,
        init_repo,
        tag,
        write,
    )

    root = init_repo(tmp_path / "ambiguous")
    write(root, "requirements.txt", "fake-dep==1.0\n")
    write(root, "dep.py", DEP_NEW)
    write(root, "app.py", APP_PLAIN)
    write(root, "probe.py", PROBE_PY)
    write(root, "regression_probe.py", REGRESSION_PY)
    commit_all(root, "old state already fixed")
    tag(root, "amb-v1.0")
    write(root, "requirements.txt", "fake-dep==1.1\n")
    write(root, "app.py", APP_PATCHED)
    write(root, "workaround.py", WORKAROUND_PY)
    commit_all(root, "downstream pins fake-dep 1.1 with workaround")
    tag(root, "amb-v2.0")

    refs = {
        "root": root, "old_tag": "amb-v1.0", "new_tag": "amb-v2.0",
        "patch": WORKAROUND_PATCH,
    }
    ctx = _context(refs, _releases())
    initial = PipelineState(workflow=WorkflowRun(id="wf:ambiguous", hypothesis_id=None))
    final = run_pipeline(initial, ctx)

    assert final.matrix[UniverseCell.B] == TestStatus.PASS  # bug does not reproduce
    assert final.candidate_id is not None  # workaround was found...
    assert final.decision is not None
    assert final.decision.outcome == DecisionOutcome.ABSTAIN  # ...but proof fails
    assert final.pr_id is None and final.pr_skipped
    assert final.workflow is not None and final.workflow.state.value == "ABSTAINED"


def test_phase2_evidence_types_cover_chain_links():
    item = make_evidence(
        id="ev:dep", evidence_type=EvidenceType.DEPENDENCY_STATE, source="reconstructor",
        claim="fake-dep==1.0 active at old state", artifact_ref="requirements.txt",
    )
    assert validate_item(item).valid
