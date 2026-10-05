"""Structured reasoning providers (Phase 3). Proposals only, never authority."""

from reasoning.base import ReasoningProvider, require_nonempty
from reasoning.errors import (
    ReasoningAuthError,
    ReasoningError,
    ReasoningMalformedError,
    ReasoningRateLimitError,
    ReasoningTimeoutError,
    ReasoningUnavailableError,
)
from reasoning.mock import MockReasoningProvider
from reasoning.models import (
    EvidenceSynthesis,
    ReasoningFailure,
    ReasoningStatus,
    ReproductionProposal,
    SynthesisAssessment,
    UpstreamAnalysis,
    WorkaroundAnalysis,
)
from reasoning.nebius import (
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT_S,
    NebiusReasoningProvider,
)

__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_TIMEOUT_S",
    "EvidenceSynthesis",
    "MockReasoningProvider",
    "NebiusReasoningProvider",
    "ReasoningAuthError",
    "ReasoningError",
    "ReasoningFailure",
    "ReasoningMalformedError",
    "ReasoningRateLimitError",
    "ReasoningStatus",
    "ReasoningTimeoutError",
    "ReasoningUnavailableError",
    "ReproductionProposal",
    "ReasoningProvider",
    "SynthesisAssessment",
    "require_nonempty",
    "UpstreamAnalysis",
    "WorkaroundAnalysis",
]
