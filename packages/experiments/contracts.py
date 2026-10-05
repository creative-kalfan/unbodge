"""Counterfactual suite/result contracts (Phase 1)."""
from __future__ import annotations

from dataclasses import dataclass, field

from domain.enums import TestStatus, UniverseCell
from domain.models import ExperimentRun, ExperimentSpec

CANONICAL_SUCCESS: dict[UniverseCell, TestStatus] = {
    UniverseCell.A: TestStatus.PASS,
    UniverseCell.B: TestStatus.FAIL,
    UniverseCell.C: TestStatus.PASS,
    UniverseCell.D: TestStatus.PASS,
}


@dataclass(frozen=True)
class CellResult:
    spec: ExperimentSpec
    run: ExperimentRun


@dataclass
class CounterfactualSuite:
    """Exactly one spec per universe cell (A, B, C, D)."""

    specs: dict[UniverseCell, ExperimentSpec] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if set(self.specs.keys()) != set(UniverseCell):
            raise ValueError(
                "counterfactual suite must contain exactly cells A, B, C, D"
            )


@dataclass
class CounterfactualResult:
    """Exactly one run per universe cell."""

    runs: dict[UniverseCell, ExperimentRun] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if set(self.runs.keys()) != set(UniverseCell):
            raise ValueError("counterfactual result must contain exactly cells A, B, C, D")

    @property
    def matrix(self) -> dict[UniverseCell, TestStatus]:
        return {cell: run.status for cell, run in self.runs.items()}

    @property
    def is_canonical_success(self) -> bool:
        return self.matrix == CANONICAL_SUCCESS


def meets_removal_bar(matrix: dict[UniverseCell, TestStatus]) -> bool:
    """Evidence bar for the counterfactual matrix.

    Requires A PASS (workaround compensates on OLD), B FAIL (bug reproduces
    without the workaround), D PASS (fix removes the need). C (NEW +
    workaround) must be PASS if present -- a C FAIL contradicts the claim
    that the fix is safe.
    """
    if (
        matrix.get(UniverseCell.A) != TestStatus.PASS
        or matrix.get(UniverseCell.B) != TestStatus.FAIL
        or matrix.get(UniverseCell.D) != TestStatus.PASS
    ):
        return False
    if UniverseCell.C in matrix and matrix[UniverseCell.C] != TestStatus.PASS:
        return False
    return True