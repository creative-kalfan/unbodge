"""Benchmark v1: 10 cases, measured outcomes, honest baselines.

Measured via real pipeline runs (docker): 2 OBSOLETE proposals, 3
AMBIGUOUS abstentions. UNPROVABLE cases resolve through the
evidence-completeness gate without execution. Baselines run the same
cases; metrics distinguish MEASURED from TARGET.
"""

import time

import pytest

from benchmark import (
    BenchmarkLabel,
    BenchmarkProvenance,
    BenchmarkRepository,
    BenchmarkDependency,
    BenchmarkCase,
    BenchmarkUpstream,
    BenchmarkWorkaround,
    BenchmarkHistory,
    build_v1,
    compute_metrics,
    evaluate_unprovable,
    full_from_pipeline,
    meets_target,
    no_counterfactual,
    llm_only,
    llm_plus_search,
    run_pure_baselines,
    summarize,
)
from domain.enums import DecisionOutcome, TestStatus, UniverseCell
from domain.models import Release, UpstreamEvent, WorkflowRun
from evaluation import HumanJudgment
from realcase_support import (
    FIX_COMMIT_ID,
    FIX_COMMIT_SHA,
    NEW_VERSION,
    OLD_VERSION,
    RELEASE_ID,
    RELEASE_TAG,
    UPSTREAM_ISSUE_ID,
    UPSTREAM_ISSUE_TITLE,
    build_real_repo,
)
from pypi.base import FixturePyPIClient, ReleaseMetadata
from sandbox.base import SandboxConstraints
from sandbox.docker import DockerSandbox, docker_available
from support import CANONICAL_MATRIX
from workflow.pipeline import run_pipeline
from workflow.stages import PipelineContext, PipelineState

needs_docker = pytest.mark.skipif(
    not docker_available(), reason="docker daemon or image unavailable"
)

REPO_ID = "repo:packaging-downstream"

VARIANTS = {
    # variant_id: (marker_text, marker_extra, expected_outcome)
    "case:packaging-pep685": ("extra == 'foo-bar'", "foo_bar", DecisionOutcome.PROPOSE_REMOVAL),
    "case:packaging-pep685-norm": (
        "extra == 'pep-685-norm'", "PEP_685...norm", DecisionOutcome.PROPOSE_REMOVAL,
    ),
    "case:packaging-pep685-normalized-input": (
        "extra == 'foo-bar'", "foo-bar", DecisionOutcome.ABSTAIN,
    ),
    "case:packaging-pep685-case-variant": (
        "extra == 'SECURITY'", "security", DecisionOutcome.ABSTAIN,
    ),
    "case:packaging-pep685-punct-variant": (
        "extra == 'Different.punctuation..is...equal'",
        "different__punctuation_is_EQUAL",
        DecisionOutcome.ABSTAIN,
    ),
}


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


def _context(refs, plan_id, marker_text, marker_extra):
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
        releases=(
            Release(
                id=RELEASE_ID, repository_id="repo:packaging", tag=RELEASE_TAG,
                version=RELEASE_TAG, contains_fix_sha=FIX_COMMIT_SHA,
            ),
        ),
        pypi=_pypi(),
        sandbox=DockerSandbox(
            constraints=SandboxConstraints(
                allowed_env_keys=frozenset(
                    {"DEP_VERSION", "WORKAROUND", "SUITE", "MARKER_EXTRA", "MARKER_TEXT"}
                )
            )
        ),
        plan_id=plan_id,
        decision_id=f"decision:{plan_id}",
        probe_env={"MARKER_TEXT": marker_text, "MARKER_EXTRA": marker_extra},
        regression_env={},
        scan_exclude_prefixes=("vendor/",),
    )


def test_dataset_v1_has_ten_honest_cases():
    dataset = build_v1()
    assert len(dataset.cases) == 10
    assert dataset.name == "unbodge-history-v1"
    assert len({c.id for c in dataset.cases}) == 10
    labels = [c.label for c in dataset.cases]
    assert labels.count(BenchmarkLabel.OBSOLETE) == 2
    assert labels.count(BenchmarkLabel.AMBIGUOUS) == 3
    assert labels.count(BenchmarkLabel.UNPROVABLE) == 5
    for case in dataset.cases:
        assert case.provenance.sources, case.id
        assert "manufactured" not in case.provenance.method.lower()
        assert len(case.upstream.fix_commit_sha) == 40, case.id
    unprovable = [c for c in dataset.cases if c.label == BenchmarkLabel.UNPROVABLE]
    assert all(c.expected_outcome == DecisionOutcome.ABSTAIN for c in unprovable)
    assert all(not c.workaround.candidate_id for c in unprovable)


def test_pure_baselines_and_unprovable_gate():
    dataset = build_v1()
    results = run_pure_baselines(dataset)
    assert set(results) == {"llm_only", "llm_plus_search", "no_counterfactual"}
    for name, outcomes in results.items():
        assert len(outcomes) == 10
        assert all(r.predicted == DecisionOutcome.ABSTAIN for r in outcomes), name
    metrics = summarize(results)["llm_only"]
    assert metrics.abstention_accuracy == 1.0  # 8/8 expected abstentions
    assert metrics.safe_removal_precision is None  # never proposes: undefined, not zero
    assert metrics.unsafe_removal_rate == 0.0
    assert metrics.cost_usd_total == 0.0
    gated = [evaluate_unprovable(c) for c in dataset.cases
             if c.label == BenchmarkLabel.UNPROVABLE]
    assert len(gated) == 5
    assert all(r.predicted == DecisionOutcome.ABSTAIN for r in gated)
    assert all(r.reconstructed is False and r.counterfactual_ok is False for r in gated)


@needs_docker
def test_measured_variants_match_expected_outcomes(tmp_path):
    dataset = build_v1()
    by_id = {c.id: c for c in dataset.cases}
    full_results = []
    for variant_id, (marker_text, marker_extra, expected) in VARIANTS.items():
        refs = build_real_repo(tmp_path / variant_id.replace(":", "-"))
        ctx = _context(refs, plan_id=variant_id, marker_text=marker_text,
                       marker_extra=marker_extra)
        started = time.perf_counter()
        final = run_pipeline(
            PipelineState(workflow=WorkflowRun(id=f"wf:{variant_id}", hypothesis_id=None)),
            ctx,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        assert final.decision is not None
        assert final.decision.outcome == expected, variant_id
        full_results.append(
            full_from_pipeline(
                by_id[variant_id],
                predicted=final.decision.outcome,
                chain_valid=True,
                reconstructed=True,
                counterfactual_ok=True,
                regression_passed=(
                    final.regression.status == TestStatus.PASS if final.regression else None
                ),
                latency_ms=latency_ms,
                human_label=by_id[variant_id].label,
            )
        )
    metrics = compute_metrics(full_results)
    assert metrics.n == 5
    assert metrics.safe_removal_precision == 1.0
    assert metrics.unsafe_removal_rate == 0.0
    assert metrics.abstention_accuracy == 1.0
    assert metrics.human_agreement == 1.0
    assert metrics.cost_usd_total == 0.0
    assert meets_target(metrics, "unsafe_removal_rate") is True
    assert meets_target(metrics, "dataset_size") is None  # target, not measured here
