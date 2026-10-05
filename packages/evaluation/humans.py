"""Human-evaluation preparation (Phase 3).

Interfaces only: labels, judgment records, and review packets. Toloka and
Tendem remain OPTIONAL and outside the mandatory runtime path -- their
adapters are disabled stubs that fail closed with a clear error. Nothing
here is imported by (or influences) the policy gate.
"""

from __future__ import annotations

from datetime import datetime

from benchmark.models import BenchmarkLabel
from domain.errors import UnbodgeError
from domain.models import UnbodgeModel, utcnow
from pydantic import Field


class EvaluationNotEnabledError(UnbodgeError):
    """An optional evaluation backend was invoked without being enabled."""


class HumanJudgment(UnbodgeModel):
    case_id: str = Field(min_length=1)
    reviewer: str = Field(min_length=1)
    label: BenchmarkLabel
    rationale: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class ReviewPacket(UnbodgeModel):
    """What a human reviewer sees: structured refs, never model verdicts."""

    case_id: str = Field(min_length=1)
    hypothesis_claim: str = ""
    matrix: dict[str, str] = Field(default_factory=dict)
    regression: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    upstream_refs: list[str] = Field(default_factory=list)


class TolokaAdapter:
    """Optional crowdsourcing backend. Disabled unless explicitly enabled."""

    def __init__(self, *, enabled: bool = False) -> None:
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    def submit(self, packet: ReviewPacket) -> str:
        if not self._enabled:
            raise EvaluationNotEnabledError(
                "toloka is optional and not enabled in Phase 3"
            )
        raise NotImplementedError("toloka transport is not implemented in Phase 3")


class TendemAdapter:
    """Optional expert-escalation backend for high-value abstentions."""

    def __init__(self, *, enabled: bool = False) -> None:
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    def escalate(self, packet: ReviewPacket, reason: str = "") -> str:
        if not self._enabled:
            raise EvaluationNotEnabledError(
                "tendem is optional and not enabled in Phase 3"
            )
        raise NotImplementedError("tendem transport is not implemented in Phase 3")


__all__ = [
    "EvaluationNotEnabledError",
    "HumanJudgment",
    "ReviewPacket",
    "TendemAdapter",
    "TolokaAdapter",
]
