"""Experiment contracts, planner and runner (Phase 1)."""
from __future__ import annotations

import re

import pytest

from domain.enums import DependencyVersion, TestStatus, UniverseCell, WorkaroundState
from domain.errors import DomainError
from experiments.contracts import (
    CounterfactualResult,
    CounterfactualSuite,
    meets_removal_bar,
)
from experiments.planner import GIT_SHAS, plan_counterfactual
from experiments.runner import execute_spec, run_regression, run_suite
from experiments.synthetic import REGRESSION_PROFILES
from support import CANONICAL_MATRIX, make_sandbox

_ = WorkaroundState  # re-exported for API stability checks


def test_planner_builds_four_cells_with_correct_mapping():
    suite = plan_counterfactual("plan:9")
    assert set(suite.specs.keys()) == set(UniverseCell)
    for cell, spec in suite.specs.items():
        assert spec.cell == cell
        assert spec.dependency_version == cell.dependency
        assert spec.workaround_state == cell.workaround
        assert spec.id == f"plan:9:cell:{cell.value}"
        assert spec.timeout_s > 0
        assert re.match(r"^[0-9a-f]{40}$", spec.git_sha or "")
        assert f"--dep {cell.dependency.value}" in spec.command
        assert f"--workaround {cell.workaround.value}" in spec.command


def test_planner_is_deterministic():
    first = plan_counterfactual("plan:9")
    second = plan_counterfactual("plan:9")
    assert first.specs == second.specs


def test_suite_rejects_incomplete_cells():
    suite = plan_counterfactual("plan:9")
    partial = {UniverseCell.A: suite.specs[UniverseCell.A]}
    with pytest.raises(ValueError):
        CounterfactualSuite(specs=partial)


def test_result_rejects_incomplete_runs():
    with pytest.raises(ValueError):
        CounterfactualResult(runs={})


def test_execute_spec_records_provenance():
    sandbox = make_sandbox()
    spec = plan_counterfactual("plan:9").specs[UniverseCell.A]
    run = execute_spec(sandbox=sandbox, spec=spec)
    assert run.spec_id == spec.id
    assert run.cell == UniverseCell.A
    assert run.status == TestStatus.PASS
    assert run.exit_code == 0
    assert run.git_sha == GIT_SHAS[DependencyVersion.OLD]
    assert run.dependency_state["fake-dep"]
    assert run.artifact_hashes  # transcripts captured
    assert "DEP_VERSION" in run.environment
    assert sandbox.active_sessions() == 0  # lifecycle cleaned up


def test_execute_spec_requires_git_sha():
    sandbox = make_sandbox()
    spec = plan_counterfactual("plan:9").specs[UniverseCell.A].model_copy(
        update={"git_sha": None}
    )
    with pytest.raises(DomainError):
        execute_spec(sandbox=sandbox, spec=spec)


def test_run_suite_matrix_matches_canonical():
    result = run_suite(sandbox=make_sandbox(), suite=plan_counterfactual("proof:x"))
    assert result.matrix == CANONICAL_MATRIX
    assert result.is_canonical_success
    assert meets_removal_bar(result.matrix)


@pytest.mark.parametrize(
    "matrix,expected",
    [
        (dict(CANONICAL_MATRIX), True),
        ({**CANONICAL_MATRIX, UniverseCell.B: TestStatus.PASS}, False),
        ({**CANONICAL_MATRIX, UniverseCell.A: TestStatus.FAIL}, False),
        ({**CANONICAL_MATRIX, UniverseCell.D: TestStatus.FAIL}, False),
        ({**CANONICAL_MATRIX, UniverseCell.C: TestStatus.FAIL}, False),
        ({k: v for k, v in CANONICAL_MATRIX.items() if k != UniverseCell.C}, True),
        ({}, False),
    ],
)
def test_removal_bar_matrix_cases(matrix, expected):
    assert meets_removal_bar(matrix) is expected


def test_run_regression_passes_on_new_without_workaround():
    reg = run_regression(
        sandbox=make_sandbox(),
        suite="fake-dep-probes",
        command="regression-suite --dep NEW --workaround ABSENT",
        env={"DEP_VERSION": "NEW", "WORKAROUND": "ABSENT"},
        git_sha=GIT_SHAS[DependencyVersion.NEW],
    )
    assert reg.status == TestStatus.PASS
    assert reg.failed == 0 and reg.passed == len(REGRESSION_PROFILES)


def test_run_regression_fails_on_old_without_workaround():
    reg = run_regression(
        sandbox=make_sandbox(),
        suite="fake-dep-probes",
        command="regression-suite --dep OLD --workaround ABSENT",
        git_sha=GIT_SHAS[DependencyVersion.OLD],
    )
    assert reg.status == TestStatus.FAIL
    assert reg.failed > 0


def test_run_regression_rejects_unparseable_output():
    def junk_handler(command, env):
        return "hello", "", 0

    sandbox = make_sandbox()
    sandbox.register_handler("synthetic-check", junk_handler)
    with pytest.raises(DomainError):
        run_regression(
            sandbox=sandbox,
            suite="s",
            command="synthetic-check --dep OLD --workaround ABSENT",
            git_sha=GIT_SHAS[DependencyVersion.OLD],
        )