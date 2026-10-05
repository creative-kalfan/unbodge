"""Benchmark runner (Phase 4).

Pure baselines run offline everywhere. Full-pipeline outcomes are
measured by tests (docker) and recorded via ``full_from_pipeline``.
UNPROVABLE cases resolve through the evidence-completeness gate without
execution: no workaround link means ABSTAIN, honestly and cheaply.
"""

from __future__ import annotations

import time

from domain.enums import DecisionOutcome

from benchmark.baselines import (
    full_from_pipeline,
    llm_only,
    llm_plus_search,
    no_counterfactual,
)
from benchmark.metrics import (
    BenchmarkResult,
    MetricsReport,
    TARGETS,
    compute_metrics,
    meets_target,
)
from benchmark.models import BenchmarkCase, BenchmarkDataset, BenchmarkLabel
from reasoning import MockReasoningProvider, ReasoningProvider
from research import MockResearchProvider, ResearchProvider


def evaluate_unprovable(case: BenchmarkCase) -> BenchmarkResult:
    """Completeness gate: without a workaround link, ABSTAIN (no docker)."""
    if case.workaround.candidate_id and case.history.old_sha and case.history.new_sha:
        raise ValueError(f"case {case.id!r} looks runnable; use the pipeline")
    return BenchmarkResult(
        case_id=case.id, predicted=DecisionOutcome.ABSTAIN,
        expected=case.expected_outcome, chain_valid=False, reconstructed=False,
        counterfactual_ok=False, regression_passed=None, latency_ms=0.0,
    )


def run_pure_baselines(
    dataset: BenchmarkDataset,
    reasoning: ReasoningProvider | None = None,
    research: ResearchProvider | None = None,
) -> dict[str, list[BenchmarkResult]]:
    reasoning = reasoning or MockReasoningProvider()
    research = research or MockResearchProvider({})
    started = time.perf_counter()
    llm = [llm_only(case, reasoning) for case in dataset.cases]
    search = [llm_plus_search(case, reasoning, research) for case in dataset.cases]
    nocf = [no_counterfactual(case) for case in dataset.cases]
    elapsed_ms = (time.perf_counter() - started) * 1000.0 / max(len(dataset.cases), 1)
    for result in (*llm, *search, *nocf):
        result.latency_ms = elapsed_ms
    return {"llm_only": llm, "llm_plus_search": search, "no_counterfactual": nocf}


def summarize(
    results_by_baseline: dict[str, list[BenchmarkResult]],
) -> dict[str, MetricsReport]:
    return {
        name: compute_metrics(results) for name, results in results_by_baseline.items()
    }


__all__ = [
    "TARGETS",
    "evaluate_unprovable",
    "full_from_pipeline",
    "meets_target",
    "run_pure_baselines",
    "summarize",
]
