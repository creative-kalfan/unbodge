"""ReasoningProvider interface (Phase 3).

Four operations, structured Pydantic I/O. Implementations (mock, Nebius)
share this ABC exactly. The provider proposes; deterministic tools verify;
evidence validates; policy decides. There is no method here that can
authorize removal, mutate evidence, or touch policy.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from reasoning.models import (
    EvidenceSynthesis,
    ReproductionProposal,
    UpstreamAnalysis,
    WorkaroundAnalysis,
)


class ReasoningProvider(ABC):
    """Structured reasoning interface (proposals only, never authority)."""

    @abstractmethod
    def analyze_upstream(
        self, *, issue_id: str, title: str, body: str = ""
    ) -> UpstreamAnalysis:
        """Propose an interpretation of an upstream issue."""
        ...

    @abstractmethod
    def analyze_workaround(
        self, *, file_path: str, snippet: str, detector: str = ""
    ) -> WorkaroundAnalysis:
        """Propose an interpretation of a workaround candidate."""
        ...

    @abstractmethod
    def generate_reproduction(
        self, *, hypothesis_id: str, claim: str, files: list[str] | None = None
    ) -> ReproductionProposal:
        """Propose a reproduction plan (executed only via sandbox)."""
        ...

    @abstractmethod
    def synthesize_evidence(
        self, *, hypothesis_id: str, evidence_ids: list[str]
    ) -> EvidenceSynthesis:
        """Propose an advisory synthesis (policy never consumes this)."""
        ...


def require_nonempty(**fields: str) -> None:
    """Shared input validation for all providers (programmer errors)."""
    for name, value in fields.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"reasoning input {name!r} must be non-empty")


__all__ = ["ReasoningProvider", "require_nonempty"]
