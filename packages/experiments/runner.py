"""Experiment execution coordination (Phase 1).

Thin wiring only: spec -> sandbox lifecycle -> run record -> evidence-ready
payloads. All pass/fail semantics come from the sandbox exit codes; no LLM,
no heuristics.
"""
from __future__ import annotations

import re
from typing import Mapping

from domain.enums import TestStatus, UniverseCell
from domain.errors import DomainError
from domain.models import ExperimentRun, ExperimentSpec, RegressionResult
from evidence.hashing import sha256_hex
from experiments.contracts import CounterfactualResult, CounterfactualSuite
from sandbox.base import Sandbox

_REGRESSION_RE = re.compile(r"passed=(?P<passed>\d+)\s+failed=(?P<failed>\d+)")


def parse_regression_counts(stdout: str) -> tuple[int, int]:
    """Parse ``passed=N failed=M`` counts; raise ``DomainError`` if absent."""
    if not stdout or not stdout.strip():
        raise DomainError("regression output is empty")
    match = _REGRESSION_RE.search(stdout)
    if match is None:
        raise DomainError(f"regression output unparseable: {stdout!r}")
    return int(match.group("passed")), int(match.group("failed"))


def execute_spec(*, sandbox: Sandbox, spec: ExperimentSpec) -> ExperimentRun:
    """Run one spec through the full sandbox lifecycle and record the run."""
    if spec.git_sha is None:
        raise DomainError(f"experiment spec {spec.id!r} is missing git_sha")
    with sandbox.session() as handle:
        result = sandbox.execute(handle, spec.command, spec.env)
        artifacts = sandbox.collect(handle)
    status = TestStatus.PASS if result.exit_code == 0 else TestStatus.FAIL
    artifact_hashes = {
        name: sha256_hex(content) for name, content in sorted(artifacts.items())
    }
    return ExperimentRun(
        id=f"{spec.id}:run",
        spec_id=spec.id,
        cell=spec.cell,
        command=spec.command,
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.exit_code,
        duration_s=max(result.duration_s, 0.0),
        status=status,
        environment=dict(result.environment),
        git_sha=spec.git_sha,
        dependency_state=dict(spec.dependency_state),
        test_report={"status": status.value, "exit_code": result.exit_code},
        artifact_hashes=artifact_hashes,
    )


def run_suite(*, sandbox: Sandbox, suite: CounterfactualSuite) -> CounterfactualResult:
    runs = {
        cell: execute_spec(sandbox=sandbox, spec=spec)
        for cell, spec in suite.specs.items()
    }
    return CounterfactualResult(runs=runs)


def run_regression(
    *,
    sandbox: Sandbox,
    suite: str,
    command: str,
    env: Mapping[str, str] | None = None,
    cell: UniverseCell = UniverseCell.D,
    run_id: str = "regression:1",
    git_sha: str,
) -> RegressionResult:
    """Execute a regression suite through the sandbox and record the result."""
    with sandbox.session() as handle:
        result = sandbox.execute(handle, command, dict(env or {}))
        sandbox.collect(handle)
    passed, failed = parse_regression_counts(result.stdout)
    if (failed == 0 and passed > 0) != (result.exit_code == 0):
        raise DomainError(
            f"regression counts contradict exit_code {result.exit_code}: {result.stdout!r}"
        )
    status = TestStatus.PASS if (failed == 0 and passed > 0) else TestStatus.FAIL
    return RegressionResult(
        id=run_id,
        suite=suite,
        cell=cell,
        passed=passed,
        failed=failed,
        status=status,
        duration_s=max(result.duration_s, 0.0),
        git_sha=git_sha,
    )