"""Phase 3 first real case: packaging PEP 685 x pip workaround (end to end).

Real history (see tests/fixtures/real_case/PROVENANCE.md):
  upstream issue  pypa/packaging#545
  fix commit      53dbb257 (2022-05-12)
  release         packaging 22.0 (2022-12-07), OLD=21.3
  downstream      pip workaround (PR #12095, pip 23.3), removed via
                  4d70566c (pip 24.1)

Expected: OLD+workaround PASS, OLD-plain FAIL, NEW+workaround PASS,
NEW-plain PASS, regression PASS, evidence VALID, PROPOSE_REMOVAL.
Ambiguous variant (normalized extra): ABSTAIN, no PR.
"""

import pytest

from benchmark import BenchmarkCase, BenchmarkDataset, BenchmarkDependency, BenchmarkHistory, BenchmarkLabel, BenchmarkProvenance, BenchmarkRepository, BenchmarkUpstream, BenchmarkWorkaround
from domain.enums import DecisionOutcome, EvidenceType, PolicyMode, TestStatus, UniverseCell
from domain.models import Release, UpstreamEvent, WorkflowRun
from evidence.chain import build_chain_graph, check_chain
from evidence.items import make_evidence
from evidence.validation import validate_item
from evaluation import HumanJudgment
from pypi.base import FixturePyPIClient, ReleaseMetadata
from realcase_support import (
    FIX_COMMIT_ID,
    FIX_COMMIT_SHA,
    NEW_VERSION,
    OLD_VERSION,
    RELEASE_ID,
    RELEASE_TAG,
    UPSTREAM_ISSUE_ID,
    UPSTREAM_ISSUE_TITLE,
    UPSTREAM_ISSUE_URL,
    build_real_repo,
)
from reasoning.mock import MockReasoningProvider
from research import MockResearchProvider, ResearchBundle, ResearchQuery, ResearchResult, research_to_evidence
from sandbox.base import SandboxConstraints
from sandbox.docker import DockerSandbox, docker_available
from support import CANONICAL_MATRIX
from tracing import LocalTracer, TraceEvent
from workflow.pipeline import run_pipeline
from workflow.stages import PipelineContext, PipelineState

needs_docker = pytest.mark.skipif(
    not docker_available(), reason="docker daemon or image unavailable"
)

REPO_ID = "repo:packaging-downstream"


def _pypi():
    from datetime import datetime, timezone

    return FixturePyPIClient(
        {
            "packaging": {
                OLD_VERSION: ReleaseMetadata(
                    name="packaging", version=OLD_VERSION,
                    upload_time=datetime(2021, 11, 17, tzinfo=timezone.utc),
                ),
                NEW_VERSION: ReleaseMetadata(
                    name="packaging", version=NEW_VERSION,
                    upload_time=datetime(2022, 12, 7, tzinfo=timezone.utc),
                ),
            }
        }
    )


def _releases():
    return (
        Release(
            id=RELEASE_ID, repository_id="repo:packaging", tag=RELEASE_TAG,
            version=RELEASE_TAG, contains_fix_sha=FIX_COMMIT_SHA,
        ),
    )


def _sandbox():
    return DockerSandbox(
        constraints=SandboxConstraints(
            allowed_env_keys=frozenset(
                {"DEP_VERSION", "WORKAROUND", "SUITE", "MARKER_EXTRA", "MARKER_TEXT"}
            )
        )
    )


def _context(refs, marker_extra="foo_bar") -> PipelineContext:
    return PipelineContext(
        repository_id=REPO_ID,
        repo_path=str(refs["root"]),
        old_rev=refs["old_tag"],
        new_rev=refs["new_tag"],
        workaround_patch=refs["patch"],
        probe_argv=["python", "check.py"],
        regression_argv=["python", "regression_markers.py"],
        event=UpstreamEvent(
            id="evt:packaging-545", repository_id="repo:packaging",
            title=UPSTREAM_ISSUE_TITLE,
        ),
        issue_id=UPSTREAM_ISSUE_ID,
        fix_id=FIX_COMMIT_ID,
        fix_sha=FIX_COMMIT_SHA,
        releases=_releases(),
        pypi=_pypi(),
        sandbox=_sandbox(),
        plan_id="phase3:packaging-pep685",
        decision_id="decision:phase3:packaging-pep685",
        probe_env={"MARKER_EXTRA": marker_extra},
        regression_env={},
        scan_exclude_prefixes=("vendor/",),
    )


def _reasoning_proposals():
    reasoning = MockReasoningProvider()
    upstream = reasoning.analyze_upstream(
        issue_id=UPSTREAM_ISSUE_ID, title=UPSTREAM_ISSUE_TITLE,
        body="markers with extras ignore PEP 685 normalization",
    )
    workaround = reasoning.analyze_workaround(
        file_path="pip_compat.py",
        snippet="compensated_evaluate with safe_extra fallback",
        detector="UpstreamReferenceDetector",
    )
    plan = reasoning.generate_reproduction(
        hypothesis_id="phase3:packaging-pep685:hyp",
        claim="compensated evaluation passes where plain evaluation fails on 21.3",
        files=["check.py", "pip_compat.py"],
    )
    synthesis = reasoning.synthesize_evidence(
        hypothesis_id="phase3:packaging-pep685:hyp", evidence_ids=["ev:1"]
    )
    return upstream, workaround, plan, synthesis


@needs_docker
def test_real_case_proposes_removal(tmp_path):
    refs = build_real_repo(tmp_path / "real-downstream")
    tracer = LocalTracer()

    with tracer.span("trace:real-case", "reasoning.upstream", issue=UPSTREAM_ISSUE_ID):
        upstream, workaround, plan, synthesis = _reasoning_proposals()
    assert not upstream.verified and upstream.uncertainties
    assert not plan.verified and plan.commands

    research = MockResearchProvider(
        {
            "packaging pep 685 extras": ResearchBundle(
                query="packaging pep 685 extras",
                results=[
                    ResearchResult(
                        id="res:545", query="packaging pep 685 extras",
                        source=UPSTREAM_ISSUE_URL, title=UPSTREAM_ISSUE_TITLE,
                        snippet="markers with extras", url=UPSTREAM_ISSUE_URL,
                        content_hash="c" * 64,
                    )
                ],
            )
        }
    )
    with tracer.span("trace:real-case", "research.search"):
        bundle = research.search(ResearchQuery(query="packaging pep 685 extras"))
    research_items = research_to_evidence(bundle)
    assert len(research_items) == 1
    assert validate_item(research_items[0]).valid
    assert research_items[0].artifact_ref == UPSTREAM_ISSUE_URL

    ctx = _context(refs)
    # proposals are explicitly unverified inputs to the operator, never proof
    assert not workaround.verified and not synthesis.verified
    initial = PipelineState(workflow=WorkflowRun(id="wf:real-case", hypothesis_id=None))
    with tracer.span("trace:real-case", "workflow.proof"):
        final = run_pipeline(initial, ctx)
    with tracer.span("trace:real-case", "policy.decision",
                     outcome=final.decision.outcome.value if final.decision else "?"):
        pass

    assert final.matrix == dict(CANONICAL_MATRIX)
    assert final.regression is not None and final.regression.status == TestStatus.PASS
    assert final.regression.passed == 8 and final.regression.failed == 0
    assert final.decision is not None
    assert final.decision.outcome == DecisionOutcome.PROPOSE_REMOVAL
    assert final.decision.policy_mode == PolicyMode.PROPOSE_ONLY
    assert final.pr_id is not None and not final.pr_skipped
    assert final.workflow is not None and final.workflow.state.value == "PR_CREATED"

    assert len(final.evidence) == 11
    for item in final.evidence:
        assert validate_item(item).valid, validate_item(item).errors
    assert check_chain(build_chain_graph(final.evidence)).valid
    assert set(final.decision.evidence_ids) == {item.id for item in final.evidence}

    # benchmark entries for the verified case
    dataset = BenchmarkDataset().add_case(
        BenchmarkCase(
            id="case:packaging-pep685",
            repository=BenchmarkRepository(id=REPO_ID, full_name="pypa/pip"),
            dependency=BenchmarkDependency(
                name="packaging", old_version=OLD_VERSION, new_version=NEW_VERSION
            ),
            upstream=BenchmarkUpstream(
                issue_id=UPSTREAM_ISSUE_ID, issue_url=UPSTREAM_ISSUE_URL,
                fix_commit_id=FIX_COMMIT_ID, fix_commit_sha=FIX_COMMIT_SHA,
                release_id=RELEASE_ID, release_tag=RELEASE_TAG,
            ),
            workaround=BenchmarkWorkaround(
                candidate_id=final.candidate_id or "cand:?",
                file_path="pip_compat.py",
                description="compensated marker evaluation",
            ),
            history=BenchmarkHistory(old_sha=refs["old_sha"], new_sha=refs["new_sha"]),
            expected_outcome=DecisionOutcome.PROPOSE_REMOVAL,
            evidence_refs=sorted(final.decision.evidence_ids),
            label=BenchmarkLabel.OBSOLETE,
            provenance=BenchmarkProvenance(
                sources=[UPSTREAM_ISSUE_URL], method="hand-verified",
            ),
        )
    )
    assert dataset.cases[0].label == BenchmarkLabel.OBSOLETE
    judgment = HumanJudgment(
        case_id="case:packaging-pep685", reviewer="alice",
        label=BenchmarkLabel.OBSOLETE, rationale="counterfactual proof holds",
    )
    assert judgment.label == dataset.cases[0].label

    assert [e.name for e in tracer.events()] == [
        "reasoning.upstream", "research.search", "workflow.proof", "policy.decision",
    ]


@needs_docker
def test_real_case_ambiguous_abstains(tmp_path):
    refs = build_real_repo(tmp_path / "real-downstream")
    ctx = _context(refs, marker_extra="foo-bar")  # already normalized: no bug to find
    initial = PipelineState(workflow=WorkflowRun(id="wf:real-ambiguous", hypothesis_id=None))
    final = run_pipeline(initial, ctx)
    assert final.matrix[UniverseCell.B] == TestStatus.PASS
    assert final.decision is not None
    assert final.decision.outcome == DecisionOutcome.ABSTAIN
    assert final.pr_id is None and final.pr_skipped
    assert final.workflow is not None and final.workflow.state.value == "ABSTAINED"


def test_research_evidence_type_is_search_result():
    item = make_evidence(
        id="ev:r", evidence_type=EvidenceType.SEARCH_RESULT, source="tavily",
        claim="release notes mention the fix", artifact_ref="https://x",
        payload={"query": "q"},
    )
    assert validate_item(item).valid
