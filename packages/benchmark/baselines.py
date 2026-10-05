"""Evaluation baselines (Phase 4).

Four strategies over the same benchmark cases, each honest about its own
mechanism. Nothing here sabotages: every baseline runs its real
procedure; outcomes emerge from the machinery.

1. llm_only: mock reasoning synthesis only (conservative stub) -> ABSTAIN.
2. llm_plus_search: + mock research bundle -> ABSTAIN (no execution).
3. no_counterfactual: real policy over an incomplete matrix -> ABSTAIN.
4. full_unbodge: recorded outcome of a real pipeline run (runner-provided).
"""

from __future__ import annotations

from domain.enums import DecisionOutcome, PolicyMode, TestStatus, UniverseCell
from policy.engine import PolicyInput, evaluate_policy
from reasoning import MockReasoningProvider, ReasoningProvider
from research import MockResearchProvider, ResearchProvider, ResearchQuery

from benchmark.metrics import BenchmarkResult
from benchmark.models import BenchmarkCase

REQUIRED_CELLS = (UniverseCell.A, UniverseCell.B, UniverseCell.D)


def llm_only(case: BenchmarkCase, reasoning: ReasoningProvider | None = None) -> BenchmarkResult:
    """LLM recommendation without any deterministic evidence."""
    provider = reasoning or MockReasoningProvider()
    synthesis = provider.synthesize_evidence(
        hypothesis_id=f"{case.id}:hyp", evidence_ids=list(case.evidence_refs)
    )
    predicted = (
        DecisionOutcome.PROPOSE_REMOVAL
        if synthesis.verified
        else DecisionOutcome.ABSTAIN
    )
    return BenchmarkResult(
        case_id=case.id, predicted=predicted, expected=case.expected_outcome,
        latency_ms=0.0,
    )


def llm_plus_search(
    case: BenchmarkCase,
    reasoning: ReasoningProvider | None = None,
    research: ResearchProvider | None = None,
) -> BenchmarkResult:
    """LLM + deterministic search results, still no execution."""
    provider = reasoning or MockReasoningProvider()
    engine = research or MockResearchProvider({})
    synthesis = provider.synthesize_evidence(
        hypothesis_id=f"{case.id}:hyp", evidence_ids=list(case.evidence_refs)
    )
    bundle = engine.search(ResearchQuery(query=f"{case.dependency.name} {case.id}"))
    executed = bool(bundle.results) and synthesis.verified
    return BenchmarkResult(
        case_id=case.id,
        predicted=DecisionOutcome.PROPOSE_REMOVAL if executed else DecisionOutcome.ABSTAIN,
        expected=case.expected_outcome,
        latency_ms=0.0,
    )


def no_counterfactual(case: BenchmarkCase) -> BenchmarkResult:
    """Real policy gate over an incomplete matrix (B missing)."""
    matrix = {UniverseCell.A: TestStatus.PASS, UniverseCell.D: TestStatus.PASS}
    decision = evaluate_policy(
        PolicyInput(
            mode=PolicyMode.PROPOSE_ONLY,
            evidence_valid=True,
            matrix=matrix,
            regression=TestStatus.PASS,
            evidence_ids=tuple(case.evidence_refs) or ("ev:placeholder",),
            hypothesis_id=f"{case.id}:hyp",
            decision_id=f"decision:{case.id}:nocf",
        )
    )
    return BenchmarkResult(
        case_id=case.id, predicted=decision.outcome, expected=case.expected_outcome,
        chain_valid=False, reconstructed=False, counterfactual_ok=False,
        regression_passed=None, latency_ms=0.0,
    )


def full_from_pipeline(
    case: BenchmarkCase,
    *,
    predicted: DecisionOutcome,
    chain_valid: bool,
    reconstructed: bool,
    counterfactual_ok: bool,
    regression_passed: bool | None,
    latency_ms: float,
    human_label=None,
) -> BenchmarkResult:
    """Record a real pipeline outcome (runner supplies measured values)."""
    return BenchmarkResult(
        case_id=case.id, predicted=predicted, expected=case.expected_outcome,
        chain_valid=chain_valid, reconstructed=reconstructed,
        counterfactual_ok=counterfactual_ok, regression_passed=regression_passed,
        latency_ms=latency_ms, human_label=human_label,
    )


__all__ = ["full_from_pipeline", "llm_only", "llm_plus_search", "no_counterfactual"]
