"""Typed sandbox errors."""
from __future__ import annotations

from domain.errors import UnbodgeError


class SandboxError(UnbodgeError):
    """Base class for sandbox failures."""


class SessionError(SandboxError):
    """Unknown, destroyed, or otherwise unusable session handle."""


class CommandRejectedError(SandboxError):
    """Command failed allowlist / syntax validation; never executed."""


class LimitViolationError(SandboxError, ValueError):
    """Resource limits or execution constraints were violated."""
