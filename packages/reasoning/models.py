"""Structured reasoning I/O contracts (Phase 3).

Every reasoning output is a typed Pydantic model. Outputs are PROPOSALS:
they carry explicit uncertainty markers (``uncertainties``,
``verified=False``) and can never authorize removal, mutate evidence, or
override deterministic validation -- the policy engine remains the sole
authority and consumes only validated evidence.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from domain.models import UnbodgeModel, utcnow
from pydantic import Field


class ReasoningStatus(str, Enum):
    OK = "OK"
    UNCERTAIN = "UNCERTAIN"


class UpstreamAnalysis(UnbodgeModel):
    issue_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    suspected_cause: str = ""
    fix_commit_id: str | None = None
    release_id: str | None = None
    behavior_change: str = ""
    uncertainties: list[str] = Field(default_factory=list)
    status: ReasoningStatus = ReasoningStatus.OK
    verified: bool = False


class WorkaroundAnalysis(UnbodgeModel):
    candidate_id: str | None = None
    file_path: str = ""
    description: str = Field(min_length=1)
    upstream_issue_id: str | None = None
    proposed_hypothesis_claim: str = ""
    uncertainties: list[str] = Field(default_factory=list)
    status: ReasoningStatus = ReasoningStatus.OK
    verified: bool = False


class ReproductionProposal(UnbodgeModel):
    hypothesis_id: str = Field(min_length=1)
    commands: list[str] = Field(min_length=1)
    files: list[str] = Field(default_factory=list)
    dependency_versions: dict[str, str] = Field(default_factory=dict)
    expected_old: str = "FAIL"
    expected_new: str = "PASS"
    test_strategy: str = ""
    uncertainties: list[str] = Field(default_factory=list)
    status: ReasoningStatus = ReasoningStatus.OK
    verified: bool = False


class SynthesisAssessment(str, Enum):
    SUPPORTS_REMOVAL = "SUPPORTS_REMOVAL"
    INSUFFICIENT = "INSUFFICIENT"
    CONTRADICTORY = "CONTRADICTORY"


class EvidenceSynthesis(UnbodgeModel):
    """Advisory synthesis only. The policy gate never consumes this model."""

    hypothesis_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    supporting_ids: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    assessment: SynthesisAssessment = SynthesisAssessment.INSUFFICIENT
    uncertainties: list[str] = Field(default_factory=list)
    status: ReasoningStatus = ReasoningStatus.OK
    verified: bool = False


class ReasoningFailure(UnbodgeModel):
    """Explicit failure/uncertainty state -- never a fake hypothesis."""

    operation: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    retryable: bool = False
    at: datetime = Field(default_factory=utcnow)


__all__ = [
    "EvidenceSynthesis",
    "ReasoningFailure",
    "ReasoningStatus",
    "ReproductionProposal",
    "SynthesisAssessment",
    "UpstreamAnalysis",
    "WorkaroundAnalysis",
]
