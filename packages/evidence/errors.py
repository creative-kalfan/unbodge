"""Typed evidence errors."""
from __future__ import annotations

from domain.errors import UnbodgeError


class EvidenceError(UnbodgeError):
    """Base class for evidence failures."""


class InvalidEvidenceError(EvidenceError):
    """Raised when evidence fails deterministic validation."""

    def __init__(self, item_id: str, errors: list[str] | tuple[str, ...]) -> None:
        self.item_id = item_id
        self.errors = tuple(errors)
        super().__init__(f"invalid evidence {item_id!r}: {'; '.join(self.errors)}")