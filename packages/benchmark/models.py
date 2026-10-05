"""Benchmark dataset foundation: unbodge-history-v1 (Phase 3).

Schema only -- no performance claims. Cases are added by verified
workflows (or tests), never manufactured to inflate size. Labels follow
the human-evaluation taxonomy.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from domain.enums import DecisionOutcome
from domain.models import UnbodgeModel, utcnow
from pydantic import Field


class BenchmarkLabel(str, Enum):
    OBSOLETE = "OBSOLETE"
    NOT_OBSOLETE = "NOT_OBSOLETE"
    AMBIGUOUS = "AMBIGUOUS"
    UNPROVABLE = "UNPROVABLE"


class BenchmarkRepository(UnbodgeModel):
    id: str = Field(min_length=1)
    full_name: str = Field(min_length=1)


class BenchmarkDependency(UnbodgeModel):
    name: str = Field(min_length=1)
    old_version: str = Field(min_length=1)
    new_version: str = Field(min_length=1)


class BenchmarkUpstream(UnbodgeModel):
    issue_id: str = Field(min_length=1)
    issue_url: str = ""
    issue_title: str = ""
    fix_commit_id: str = Field(min_length=1)
    fix_commit_sha: str = Field(min_length=1)
    release_id: str = Field(min_length=1)
    release_tag: str = Field(min_length=1)


class BenchmarkWorkaround(UnbodgeModel):
    candidate_id: str = ""
    file_path: str = ""
    description: str = ""


class BenchmarkHistory(UnbodgeModel):
    old_sha: str = ""
    new_sha: str = ""


class BenchmarkProvenance(UnbodgeModel):
    sources: list[str] = Field(default_factory=list)
    method: str = ""
    verified_at: datetime = Field(default_factory=utcnow)


class BenchmarkCase(UnbodgeModel):
    id: str = Field(min_length=1)
    repository: BenchmarkRepository
    dependency: BenchmarkDependency
    upstream: BenchmarkUpstream
    workaround: BenchmarkWorkaround
    history: BenchmarkHistory = Field(default_factory=BenchmarkHistory)
    expected_outcome: DecisionOutcome = DecisionOutcome.ABSTAIN
    evidence_refs: list[str] = Field(default_factory=list)
    label: BenchmarkLabel = BenchmarkLabel.UNPROVABLE
    provenance: BenchmarkProvenance = Field(default_factory=BenchmarkProvenance)


class BenchmarkDataset(UnbodgeModel):
    name: str = "unbodge-history-v1"
    version: str = "0.1.0"
    cases: list[BenchmarkCase] = Field(default_factory=list)

    def add_case(self, case: BenchmarkCase) -> BenchmarkDataset:
        if any(existing.id == case.id for existing in self.cases):
            raise ValueError(f"duplicate benchmark case id: {case.id!r}")
        return BenchmarkDataset(
            name=self.name, version=self.version, cases=[*self.cases, case]
        )


__all__ = [
    "BenchmarkCase",
    "BenchmarkDataset",
    "BenchmarkDependency",
    "BenchmarkHistory",
    "BenchmarkLabel",
    "BenchmarkProvenance",
    "BenchmarkRepository",
    "BenchmarkUpstream",
    "BenchmarkWorkaround",
]
