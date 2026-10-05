"""Evidence chain, local PR generation, and pipeline mechanics."""

import pytest

from domain.enums import DecisionOutcome, EvidenceType, PolicyMode, TestStatus, UniverseCell
from domain.models import EvidenceItem, RemovalDecision
from evidence.chain import (
    CHAIN_RELATIONS,
    build_chain_graph,
    build_proof_graph,
    check_chain,
    run_payload,
)
from evidence.items import make_evidence
from github.git import GitRepo
from phase2_support import build_downstream_fixture
from pr.generator import LocalPrGenerator, PrGeneratorError, render_pr_body
from workflow.pipeline import run_pipeline
from workflow.stages import (
    STAGE_FNS,
    STAGE_NAMES,
    PipelineContext,
    PipelineState,
)

CANONICAL = {
    UniverseCell.A: TestStatus.PASS,
    UniverseCell.B: TestStatus.FAIL,
    UniverseCell.C: TestStatus.PASS,
    UniverseCell.D: TestStatus.PASS,
}


def _item(seed: str, evidence_type=EvidenceType.CODE_REFERENCE) -> EvidenceItem:
    return make_evidence(
        id=seed, evidence_type=evidence_type, source="test", claim=f"claim {seed}"
    )


def test_chain_relations_and_validation():
    items = [_item(f"ev:{i}") for i in range(4)]
    graph = build_chain_graph(items)
    assert [link.relation for link in graph.links] == list(CHAIN_RELATIONS[:3])
    assert check_chain(graph).valid
    with pytest.raises(ValueError):
        build_chain_graph(items[:1])


def test_long_chain_uses_supports_fallback():
    items = [_item(f"ev:{i}") for i in range(len(CHAIN_RELATIONS) + 3)]
    graph = build_chain_graph(items)
    assert graph.links[-1].relation == "supports"
    assert check_chain(graph).valid


def test_build_proof_graph_custom_links():
    items = [_item("a"), _item("b")]
    graph = build_proof_graph(items, [("a", "b", "custom-rel")])
    assert graph.links[0].relation == "custom-rel"
    assert check_chain(graph).valid


def test_run_payload_covers_experiment_metadata():
    from domain.models import ExperimentRun
    from evidence.validation import EXPERIMENT_METADATA_KEYS
    from support import GIT_BY_CELL

    run = ExperimentRun(
        id="run:1", spec_id="spec:1", cell=UniverseCell.A,
        command="synthetic-check --dep OLD --workaround PRESENT",
        stdout="ok", stderr="", exit_code=0, duration_s=0.1,
        status=TestStatus.PASS, environment={"DEP_VERSION": "OLD"},
        git_sha=GIT_BY_CELL[UniverseCell.A],
        dependency_state={"fake-dep": "fake-dep==1.0"},
        test_report={"status": "PASS", "exit_code": 0},
        artifact_hashes={"exec-0.json": "a" * 64},
    )
    payload = run_payload(run)
    for key in EXPERIMENT_METADATA_KEYS:
        assert key in payload


def test_render_pr_body_deterministic_and_complete():
    kwargs = dict(
        hypothesis_id="hyp:1", matrix=dict(CANONICAL),
        regression_suite="regression-probes", regression_passed=3, regression_failed=0,
        evidence_ids=("ev:a", "ev:b"), fix_sha="c" * 40, release_tag="v1.1",
        removed_files=["workaround.py"],
    )
    first = render_pr_body(**kwargs)
    assert render_pr_body(**kwargs) == first
    for needle in ("A=PASS", "B=FAIL", "C=PASS", "D=PASS", "passed=3 failed=0",
                   "ev:a", "c" * 40, "v1.1", "workaround.py"):
        assert needle in first


def test_local_pr_generator_creates_branch_and_commit(tmp_path):
    refs = build_downstream_fixture(tmp_path / "downstream")
    git = GitRepo(refs["root"])
    decision = RemovalDecision(
        id="decision:1", hypothesis_id="hyp:1", outcome=DecisionOutcome.PROPOSE_REMOVAL,
        policy_mode=PolicyMode.PROPOSE_ONLY, rationale="proof holds",
        evidence_ids=["ev:a"],
    )
    pr = LocalPrGenerator(git).create_proposal(
        decision=decision, title="Remove obsolete workaround", body="Matrix: A=PASS",
        files={"app.py": "new content\n"}, base_branch="main",
    )
    assert pr.decision_id == decision.id
    assert pr.base == "main" and pr.branch.startswith("unbodge/")
    assert git.file_at(pr.branch, "app.py") == "new content\n"
    from phase2_support import git_cmd

    assert git_cmd(refs["root"], "rev-parse", "--abbrev-ref", "HEAD").strip() == "main"
    with pytest.raises(PrGeneratorError):
        LocalPrGenerator(git).create_proposal(
            decision=decision, title="  ", body="b", files={"a.py": "x"})
    with pytest.raises(PrGeneratorError):
        LocalPrGenerator(git).create_proposal(
            decision=decision, title="t", body="b", files={})


def test_pipeline_rejects_unknown_stages_and_skips_completed():
    with pytest.raises(ValueError):
        run_pipeline(PipelineState(), _ctx(), stages=("nope",))
    done = PipelineState(completed_stages=("ingest_event",))
    assert run_pipeline(done, _ctx(), stages=("ingest_event",)) == done


def test_stage_registry_matches_names():
    assert set(STAGE_FNS) == set(STAGE_NAMES) and len(STAGE_NAMES) == 13


def _ctx():
    from domain.models import UpstreamEvent

    return PipelineContext(
        repository_id="repo:x", repo_path=".", old_rev="v1", new_rev="v2",
        workaround_patch="p", probe_argv=["python", "probe.py"],
        regression_argv=["python", "regression_probe.py"],
        event=UpstreamEvent(id="evt:1", repository_id="repo:x", title="t"),
        issue_id="issue:1", fix_id="fix:1", fix_sha="c" * 40,
    )
