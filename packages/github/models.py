"""GitHub-side typed models (Phase 2).

Additive to the Phase 1 domain: new models live here so the Phase 1
``domain.models`` contract is not modified. Reuses ``UnbodgeModel``
(``extra="forbid"``) for consistent validation behavior.
"""

from __future__ import annotations

from domain.models import UnbodgeModel, utcnow
from pydantic import Field
from datetime import datetime

_SHA40 = r"^[0-9a-f]{40}$"


class IssueComment(UnbodgeModel):
    id: str = Field(min_length=1)
    issue_id: str = Field(min_length=1)
    repository_id: str = Field(min_length=1)
    author: str = Field(min_length=1)
    body: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class PullRequest(UnbodgeModel):
    id: str = Field(min_length=1)
    repository_id: str = Field(min_length=1)
    number: int = Field(gt=0)
    title: str = Field(min_length=1)
    body: str = ""
    head_branch: str = Field(min_length=1)
    base_branch: str = Field(default="main", min_length=1)
    state: str = Field(default="open", pattern=r"^(open|closed|merged)$")
    created_at: datetime = Field(default_factory=utcnow)


class PullRequestFile(UnbodgeModel):
    path: str = Field(min_length=1)
    status: str = Field(default="modified", pattern=r"^(added|modified|removed)$")
    additions: int = Field(default=0, ge=0)
    deletions: int = Field(default=0, ge=0)


class Tag(UnbodgeModel):
    name: str = Field(min_length=1)
    repository_id: str = Field(min_length=1)
    commit_sha: str = Field(pattern=_SHA40)


__all__ = ["IssueComment", "PullRequest", "PullRequestFile", "Tag"]
