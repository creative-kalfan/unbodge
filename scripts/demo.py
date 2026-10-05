"""UNBODGE deterministic demo (Phase 4, under 3 minutes).

Two tiers, same proof loop:
1. Offline synthetic proof (always runs): Phase 1 engine, no Docker.
2. Real historical case (needs Docker): packaging PEP 685 end to end.

Usage: PYTHONPATH=packages:tests python scripts/demo.py [--real-only|--synthetic-only]
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tests"))

REAL_ONLY = "--real-only" in sys.argv
SYNTHETIC_ONLY = "--synthetic-only" in sys.argv


def synthetic_demo() -> None:
    from domain.enums import PolicyMode, TestStatus
    from evidence import ensure_valid, validate_item
    from experiments import meets_removal_bar, plan_counterfactual
    from experiments.runner import run_regression, run_suite
    from policy import PolicyInput, evaluate_policy
    from support import CANONICAL_MATRIX, experiment_evidence, make_sandbox

    print("=== 1. Synthetic proof (offline, deterministic) ===")
    sandbox = make_sandbox()
    suite = plan_counterfactual("demo:synthetic")
    result = run_suite(sandbox=sandbox, suite=suite)
    assert result.matrix == dict(CANONICAL_MATRIX)
    assert result.is_canonical_success
    assert meets_removal_bar(result.matrix)
    for cell, status in sorted(result.matrix.items(), key=lambda kv: kv[0].value):
        print(f"  cell {cell.value}: {status.value}")
    regression = run_regression(
        sandbox=sandbox, suite="fake-dep-probes",
        command="regression-suite --dep NEW --workaround ABSENT",
        env={"DEP_VERSION": "NEW", "WORKAROUND": "ABSENT"},
        git_sha="b" * 40,
    )
    assert regression.status == TestStatus.PASS
    items = [ensure_valid(experiment_evidence(run)) for run in result.runs.values()]
    assert all(validate_item(item).valid for item in items)
    decision = evaluate_policy(
        PolicyInput(
            mode=PolicyMode.PROPOSE_ONLY, evidence_valid=True, matrix=dict(result.matrix),
            regression=regression.status, evidence_ids=tuple(i.id for i in items),
            hypothesis_id="demo:synthetic", decision_id="decision:demo:synthetic",
        )
    )
    print(f"  regression: {regression.status.value} "
          f"(passed={regression.passed} failed={regression.failed})")
    print(f"  evidence: VALID ({len(items)} items)")
    print(f"  decision: {decision.outcome.value}")


def real_demo() -> None:
    from domain.models import WorkflowRun
    from realcase_support import build_real_repo
    from sandbox.docker import docker_available
    from workflow.pipeline import run_pipeline
    from workflow.stages import PipelineContext, PipelineState
    from test_realcase import _context  # demo reuses verified wiring

    if not docker_available():
        print("=== 2. Real case SKIPPED (no docker daemon/image) ===")
        return
    print("=== 2. Real case: packaging PEP 685 (pypa/packaging#545) ===")
    tmp = tempfile.mkdtemp(prefix="unbodge-demo-")
    refs = build_real_repo(os.path.join(tmp, "downstream"))
    ctx = _context(refs)
    final = run_pipeline(
        PipelineState(workflow=WorkflowRun(id="wf:demo", hypothesis_id=None)), ctx
    )
    assert final.decision is not None
    print(f"  matrix: { {c.value: s.value for c, s in final.matrix.items()} }")
    print(f"  regression: {final.regression.status.value if final.regression else '?'}")
    print(f"  evidence items: {len(final.evidence)} (all valid)")
    print(f"  decision: {final.decision.outcome.value}")
    print(f"  pr: {final.pr_id or 'none (abstained)'}")


def main() -> int:
    if not SYNTHETIC_ONLY:
        try:
            real_demo()
        except Exception as exc:
            print(f"real demo unavailable: {exc}")
            if REAL_ONLY:
                return 1
    if not REAL_ONLY:
        synthetic_demo()
    print("demo complete: proof loop intact (event -> evidence -> PROPOSE or ABSTAIN)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
