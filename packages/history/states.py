"""Historical state contracts (Phase 2).

A ``HistoricalState`` is the explicit, reproducible answer to "what did
the world look like at this commit": the resolved Git SHA, the tag (if
any), and the exact dependency lock active at that point.
"""

from __future__ import annotations

from domain.errors import UnbodgeError
from domain.models import UnbodgeModel, utcnow
from pydantic import Field
from datetime import datetime

_SHA40 = r"^[0-9a-f]{40}$"


class HistoryError(UnbodgeError):
    """Historical reconstruction failed (missing state, unreadable lock)."""


class DependencyLock(UnbodgeModel):
    """Exact pinned versions: ``{normalized_name: version}``."""

    packages: dict[str, str] = Field(default_factory=dict)
    source_files: list[str] = Field(default_factory=list)

    def version_of(self, package: str) -> str | None:
        return self.packages.get(package.strip().lower().replace("_", "-"))


class HistoricalState(UnbodgeModel):
    id: str = Field(min_length=1)
    repository_id: str = Field(min_length=1)
    git_sha: str = Field(pattern=_SHA40)
    tag: str | None = None
    lock: DependencyLock = Field(default_factory=DependencyLock)
    constraints: list[str] = Field(default_factory=list)
    reconstructed_at: datetime = Field(default_factory=utcnow)


class DependencyDiff(UnbodgeModel):
    old_sha: str = Field(pattern=_SHA40)
    new_sha: str = Field(pattern=_SHA40)
    added: dict[str, str] = Field(default_factory=dict)
    removed: dict[str, str] = Field(default_factory=dict)
    changed: dict[str, tuple[str, str]] = Field(default_factory=dict)


class InstallabilityReport(UnbodgeModel):
    state_id: str = Field(min_length=1)
    installable: bool
    missing: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


__all__ = [
    "DependencyDiff",
    "DependencyLock",
    "HistoricalState",
    "HistoryError",
    "InstallabilityReport",
]
