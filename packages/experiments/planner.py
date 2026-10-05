"""Deterministic counterfactual planner (Phase 1)."""
from __future__ import annotations

from domain.enums import DependencyVersion, UniverseCell
from domain.errors import DomainError
from domain.models import ExperimentSpec
from experiments.contracts import CounterfactualSuite
from experiments.synthetic import (
    NEW_DEPENDENCY_LABEL,
    OLD_DEPENDENCY_LABEL,
    SYNTHETIC_COMMANDS,
)

OLD_GIT_SHA = "1" * 40
NEW_GIT_SHA = "2" * 40

GIT_SHAS: dict[DependencyVersion, str] = {
    DependencyVersion.OLD: OLD_GIT_SHA,
    DependencyVersion.NEW: NEW_GIT_SHA,
}

DEPENDENCY_LABELS: dict[DependencyVersion, str] = {
    DependencyVersion.OLD: OLD_DEPENDENCY_LABEL,
    DependencyVersion.NEW: NEW_DEPENDENCY_LABEL,
}


def plan_counterfactual(
    plan_id: str,
    *,
    tool: str = "synthetic-check",
    env: dict[str, str] | None = None,
    timeout_s: int = 30,
) -> CounterfactualSuite:
    """Build the four canonical universe cells for ``plan_id`` (deterministic)."""
    if tool not in SYNTHETIC_COMMANDS:
        raise DomainError(f"unknown experiment tool: {tool!r}")
    specs: dict[UniverseCell, ExperimentSpec] = {}
    for cell in UniverseCell:
        dependency = cell.dependency
        workaround = cell.workaround
        command = f"{tool} --dep {dependency.value} --workaround {workaround.value}"
        cell_env = dict(env) if env else {}
        cell_env.setdefault("DEP_VERSION", dependency.value)
        cell_env.setdefault("WORKAROUND", workaround.value)
        specs[cell] = ExperimentSpec(
            id=f"{plan_id}:cell:{cell.value}",
            plan_id=plan_id,
            cell=cell,
            dependency_version=dependency,
            workaround_state=workaround,
            command=command,
            env=cell_env,
            timeout_s=timeout_s,
            git_sha=GIT_SHAS[dependency],
            dependency_state={"fake-dep": DEPENDENCY_LABELS[dependency]},
        )
    return CounterfactualSuite(specs=specs)