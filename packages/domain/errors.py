"""Typed domain errors for UNBODGE Phase 1.

Union module: the three core errors below are the Phase 1 contract used by
this implementation. The additional error types are preserved for
compatibility with alternate tooling/sessions sharing this tree; all are
trivial typed subclasses of :class:`UnbodgeError`.
"""
from __future__ import annotations


class UnbodgeError(Exception):
    """Base class for all UNBODGE errors."""


class DomainError(UnbodgeError):
    """Base class for domain-contract violations."""


class InvalidTransitionError(DomainError):
    """Raised when a workflow transition is not in the explicit transition table."""

    def __init__(self, from_state: object, to_state: object) -> None:
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(f"invalid workflow transition: {from_state} -> {to_state}")


class EvidenceValidationError(UnbodgeError):
    """Raised when evidence fails deterministic validation."""


class ExperimentConfigError(UnbodgeError):
    """Raised when an experiment specification is inconsistent."""


class SandboxError(UnbodgeError):
    """Base class for sandbox lifecycle/contract violations (domain-level alias)."""


class SandboxCommandRejectedError(SandboxError):
    """A command failed sandbox validation and was never executed."""


class SandboxTimeoutError(SandboxError):
    """A sandboxed execution exceeded its timeout."""


class SandboxResourceLimitError(SandboxError):
    """A sandboxed execution violated a resource limit."""


class PolicyViolationError(UnbodgeError):
    """Raised when a decision violates the deterministic policy gate."""