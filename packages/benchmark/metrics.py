"""Benchmark metrics (Phase 4).

Measured values only -- see ``TARGETS`` for aspirations, never presented
as results. Undefined ratios over empty denominators are ``None``, except
``unsafe_removal_rate`` which is ``0.0`` when nothing was ever proposed
(no unsafe removal could have occurred).
"""

from __future__ import annotations

from domain.enums import DecisionOutcome
from domain.models import UnbodgeModel
from pydantic import Field

from benchmark.models import BenchmarkLabel


class BenchmarkResult(UnbodgeModel):
    case_id: str = Field(min_length=1)
    predicted: DecisionOutcome
    expected: DecisionOutcome
    chain_valid: bool = False
    reconstructed: bool = False
    counterfactual_ok: bool = False
    regression_passed: bool | None = None
    latency_ms: float = Field(ge=0.0)
    cost_usd: float = Field(default=0.0, ge=0.0)
    human_label: BenchmarkLabel | None = None


class MetricsReport(UnbodgeModel):
    n: int = Field(ge=0)
    safe_removal_precision: float | None = None
    abstention_accuracy: float | None = None
    causal_link_accuracy: float | None = None
    historical_reconstruction_success: float | None = None
    counterfactual_success: float | None = None
    regression_pass_rate: float | None = None
    unsafe_removal_rate: float | None = None
    human_agreement: float | None = None
    latency_ms_mean: float | None = None
    cost_usd_total: float | None = None
    time_saved_hours_estimate: float | None = None


#: Aspirational thresholds. Compare via ``meets_target``; never report as measured.
TARGETS: dict[str, float] = {
    "safe_removal_precision": 0.95,
    "abstention_accuracy": 0.90,
    "causal_link_accuracy": 0.90,
    "historical_reconstruction_success": 0.90,
    "counterfactual_success": 0.90,
    "regression_pass_rate": 0.95,
    "unsafe_removal_rate": 0.0,
    "human_agreement": 0.85,
    "dataset_size": 30,
}

#: Rough manual-triage cost avoided per correct removal proposal (estimate).
HOURS_SAVED_PER_REMOVAL = 2.0


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _human_agrees(result: BenchmarkResult) -> float:
    if result.predicted == DecisionOutcome.PROPOSE_REMOVAL:
        return 1.0 if result.human_label == BenchmarkLabel.OBSOLETE else 0.0
    return 1.0 if result.human_label != BenchmarkLabel.OBSOLETE else 0.0


def compute_metrics(results: list[BenchmarkResult]) -> MetricsReport:
    proposed = [r for r in results if r.predicted == DecisionOutcome.PROPOSE_REMOVAL]
    expected_propose = [r for r in results if r.expected == DecisionOutcome.PROPOSE_REMOVAL]
    expected_abstain = [r for r in results if r.expected == DecisionOutcome.ABSTAIN]
    tp = [r for r in proposed if r.expected == DecisionOutcome.PROPOSE_REMOVAL]
    regressions = [r for r in results if r.regression_passed is not None]
    human = [r for r in results if r.human_label is not None]
    return MetricsReport(
        n=len(results),
        safe_removal_precision=(len(tp) / len(proposed)) if proposed else None,
        abstention_accuracy=(
            len([r for r in expected_abstain if r.predicted == DecisionOutcome.ABSTAIN])
            / len(expected_abstain)
            if expected_abstain
            else None
        ),
        causal_link_accuracy=_mean([1.0 if r.chain_valid else 0.0 for r in results]),
        historical_reconstruction_success=_mean(
            [1.0 if r.reconstructed else 0.0 for r in results]
        ),
        counterfactual_success=_mean(
            [1.0 if r.counterfactual_ok else 0.0 for r in results]
        ),
        regression_pass_rate=_mean(
            [1.0 if r.regression_passed else 0.0 for r in regressions]
        ),
        unsafe_removal_rate=(
            (len(proposed) - len(tp)) / len(proposed) if proposed else 0.0
        ),
        human_agreement=(
            _mean([_human_agrees(r) for r in human]) if human else None
        ),
        latency_ms_mean=_mean([r.latency_ms for r in results]),
        cost_usd_total=sum(r.cost_usd for r in results),
        time_saved_hours_estimate=len(tp) * HOURS_SAVED_PER_REMOVAL if tp else 0.0,
    )


def meets_target(metrics: MetricsReport, name: str) -> bool | None:
    """Compare a measured metric against its target (None if unmeasured)."""
    value = getattr(metrics, name, None)
    target = TARGETS.get(name)
    if value is None or target is None:
        return None
    if name == "unsafe_removal_rate":
        return bool(value <= target)
    return bool(value >= target)


__all__ = [
    "HOURS_SAVED_PER_REMOVAL",
    "TARGETS",
    "BenchmarkResult",
    "MetricsReport",
    "compute_metrics",
    "meets_target",
]
