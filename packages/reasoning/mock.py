"""Deterministic mock reasoning provider (Phase 3).

Same interface as the real provider, zero network, zero credentials.
Outputs are explicitly unverified proposals (``verified=False`` plus
recorded uncertainties) -- the mock never pretends its hypotheses are
verified facts.
"""

from __future__ import annotations

from reasoning.base import ReasoningProvider, require_nonempty
from reasoning.models import (
    EvidenceSynthesis,
    ReasoningStatus,
    ReproductionProposal,
    SynthesisAssessment,
    UpstreamAnalysis,
    WorkaroundAnalysis,
)


class MockReasoningProvider(ReasoningProvider):
    """Canned deterministic proposals for tests and offline runs."""

    def analyze_upstream(
        self, *, issue_id: str, title: str, body: str = ""
    ) -> UpstreamAnalysis:
        require_nonempty(issue_id=issue_id, title=title)
        return UpstreamAnalysis(
            issue_id=issue_id,
            summary=f"mock interpretation of {title!r}",
            suspected_cause="mock suspected cause (unverified)",
            uncertainties=["mock output: cause not verified against history"],
            status=ReasoningStatus.UNCERTAIN,
            verified=False,
        )

    def analyze_workaround(
        self, *, file_path: str, snippet: str, detector: str = ""
    ) -> WorkaroundAnalysis:
        require_nonempty(file_path=file_path, snippet=snippet)
        return WorkaroundAnalysis(
            file_path=file_path,
            description=f"mock workaround analysis via {detector or 'unknown detector'}",
            uncertainties=["mock output: upstream link not verified"],
            status=ReasoningStatus.UNCERTAIN,
            verified=False,
        )

    def generate_reproduction(
        self, *, hypothesis_id: str, claim: str, files: list[str] | None = None
    ) -> ReproductionProposal:
        require_nonempty(hypothesis_id=hypothesis_id, claim=claim)
        return ReproductionProposal(
            hypothesis_id=hypothesis_id,
            commands=["python probe.py"],
            files=list(files or []),
            expected_old="FAIL",
            expected_new="PASS",
            test_strategy="execute probe in OLD/NEW sandboxes (mock proposal)",
            uncertainties=["mock output: plan not executed"],
            status=ReasoningStatus.UNCERTAIN,
            verified=False,
        )

    def synthesize_evidence(
        self, *, hypothesis_id: str, evidence_ids: list[str]
    ) -> EvidenceSynthesis:
        require_nonempty(hypothesis_id=hypothesis_id)
        return EvidenceSynthesis(
            hypothesis_id=hypothesis_id,
            summary="mock advisory synthesis (not policy input)",
            supporting_ids=list(evidence_ids),
            gaps=["mock output: gaps not assessed"],
            assessment=SynthesisAssessment.INSUFFICIENT,
            uncertainties=["mock output is advisory only"],
            status=ReasoningStatus.UNCERTAIN,
            verified=False,
        )


__all__ = ["MockReasoningProvider"]
