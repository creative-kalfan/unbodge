"""Benchmark dataset foundation (Phase 3). Schema only, no metric claims."""

from benchmark.baselines import (
    full_from_pipeline,
    llm_only,
    llm_plus_search,
    no_counterfactual,
)
from benchmark.metrics import (
    HOURS_SAVED_PER_REMOVAL,
    TARGETS,
    BenchmarkResult,
    MetricsReport,
    compute_metrics,
    meets_target,
)
from benchmark.models import (
    BenchmarkCase,
    BenchmarkDataset,
    BenchmarkDependency,
    BenchmarkHistory,
    BenchmarkLabel,
    BenchmarkProvenance,
    BenchmarkRepository,
    BenchmarkUpstream,
    BenchmarkWorkaround,
)
from benchmark.runner import evaluate_unprovable, run_pure_baselines, summarize
from benchmark.v1 import build_v1

__all__ = [
    "BenchmarkCase",
    "BenchmarkDataset",
    "BenchmarkDependency",
    "BenchmarkHistory",
    "BenchmarkLabel",
    "BenchmarkProvenance",
    "BenchmarkRepository",
    "BenchmarkUpstream",
    "BenchmarkWorkaround",
    "BenchmarkResult",
    "HOURS_SAVED_PER_REMOVAL",
    "MetricsReport",
    "TARGETS",
    "build_v1",
    "compute_metrics",
    "evaluate_unprovable",
    "full_from_pipeline",
    "llm_only",
    "llm_plus_search",
    "meets_target",
    "no_counterfactual",
    "run_pure_baselines",
    "summarize",
]
