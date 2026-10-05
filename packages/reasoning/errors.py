"""Reasoning errors (Phase 3). Failures are typed, never silent."""

from __future__ import annotations

from domain.errors import UnbodgeError


class ReasoningError(UnbodgeError):
    """Base class for reasoning provider failures."""


class ReasoningAuthError(ReasoningError):
    """Missing/invalid credentials or unconfigured provider."""


class ReasoningTimeoutError(ReasoningError):
    """The provider call exceeded its deadline."""


class ReasoningRateLimitError(ReasoningError):
    """The provider throttled the request (retryable)."""


class ReasoningMalformedError(ReasoningError):
    """Transport worked but the structured output did not validate."""


class ReasoningUnavailableError(ReasoningError):
    """Model/service unavailable or unknown failure."""


__all__ = [
    "ReasoningAuthError",
    "ReasoningError",
    "ReasoningMalformedError",
    "ReasoningRateLimitError",
    "ReasoningTimeoutError",
    "ReasoningUnavailableError",
]
