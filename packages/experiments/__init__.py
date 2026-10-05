"""Counterfactual experiment contracts, planner, runner and synthetic scenario."""
from experiments.contracts import (
    CellResult,
    CounterfactualResult,
    CounterfactualSuite,
    meets_removal_bar,
)
from experiments.planner import GIT_SHAS, plan_counterfactual
from experiments.real import (
    apply_patch,
    dependency_label_at,
    ensure_workaround_state,
    patch_marker_files,
    prepare_cell_workdir,
    read_workdir_files,
    run_real_suite,
)
from experiments.runner import (
    execute_spec,
    parse_regression_counts,
    run_regression,
    run_suite,
)
from experiments.synthetic import (
    SYNTHETIC_COMMANDS,
    RegressionOutcome,
    SyntheticOutcome,
    parse_synthetic_command,
    regression_handler,
    run_regression_checks,
    run_synthetic,
    synthetic_handler,
)

__all__ = [
    "CellResult",
    "CounterfactualResult",
    "CounterfactualSuite",
    "GIT_SHAS",
    "RegressionOutcome",
    "SyntheticOutcome",
    "SYNTHETIC_COMMANDS",
    "apply_patch",
    "dependency_label_at",
    "ensure_workaround_state",
    "execute_spec",
    "meets_removal_bar",
    "parse_regression_counts",
    "parse_synthetic_command",
    "patch_marker_files",
    "plan_counterfactual",
    "prepare_cell_workdir",
    "read_workdir_files",
    "regression_handler",
    "run_real_suite",
    "run_regression",
    "run_regression_checks",
    "run_suite",
    "run_synthetic",
    "synthetic_handler",
]