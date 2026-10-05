"""Pydantic domain contracts for UNBODGE Phase 1.

Every model is minimal: only fields justified by the Phase 1 contracts
(workflow, counterfactual proof, evidence, regression, policy). All models
reject unknown fields (``extra="forbid"``) and are JSON-serializable.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from domain.enums import (
    DecisionOutcome,
    DependencyVersion,
    EvidenceType,
    IssueState,
    PolicyMode,
    ReviewVerdict,
    TestStatus,
    UniverseCell,
    WorkaroundState,
)
from domain.states import WorkflowState, transition

_SHA40 = r"^[0-9a-f]{40}$"
_HASH64 = r"^[0-9a-f]{64}$"
_DRIVE_RE = r"^[A-Za-z]:"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UnbodgeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Repository(UnbodgeModel):
    id: str = Field(min_length=1)
    full_name: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    url: str | None = Field(default=None, pattern=r"^https?://\S+$")
    default_branch: str = "main"


class UpstreamEvent(UnbodgeModel):
    id: str = Field(min_length=1)
    repository_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    body: str = ""
    source: str = "github"
    created_at: datetime = Field(default_factory=utcnow)


class UpstreamIssue(UnbodgeModel):
    id: str = Field(min_length=1)
    repository_id: str = Field(min_length=1)
    number: int = Field(gt=0)
    title: str = Field(min_length=1)
    body: str = ""
    state: IssueState = IssueState.OPEN
    url: str | None = Field(default=None, pattern=r"^https?://\S+$")


class FixCommit(UnbodgeModel):
    id: str = Field(min_length=1)
    repository_id: str = Field(min_length=1)
    sha: str = Field(pattern=_SHA40)
    message: str = Field(min_length=1)
    author: str = ""
    committed_at: datetime = Field(default_factory=utcnow)


class Release(UnbodgeModel):
    id: str = Field(min_length=1)
    repository_id: str = Field(min_length=1)
    tag: str = Field(min_length=1)
    version: str = Field(min_length=1)
    published_at: datetime = Field(default_factory=utcnow)
    contains_fix_sha: str | None = Field(default=None, pattern=_SHA40)


class WorkaroundCandidate(UnbodgeModel):
    id: str = Field(min_length=1)
    repository_id: str = Field(min_length=1)
    file_path: str = Field(min_length=1)
    start_line: int = Field(gt=0)
    end_line: int = Field(gt=0)
    description: str = Field(min_length=1)
    detector: str = Field(min_length=1)

    @field_validator("file_path")
    @classmethod
    def _path_is_relative(cls, value: str) -> str:
        if (
            value.startswith("/")
            or value.startswith("\\")
            or ".." in value.replace("\\", "/").split("/")
            or re.match(_DRIVE_RE, value)
        ):
            raise ValueError("file_path must be a relative path without '..' segments")
        return value

    @model_validator(mode="after")
    def _lines_ordered(self) -> WorkaroundCandidate:
        if self.end_line < self.start_line:
            raise ValueError("end_line must be >= start_line")
        return self


class CausalHypothesis(UnbodgeModel):
    id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    issue_id: str = Field(min_length=1)
    fix_commit_id: str | None = None
    release_id: str | None = None
    claim: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class ReproductionPlan(UnbodgeModel):
    id: str = Field(min_length=1)
    hypothesis_id: str = Field(min_length=1)
    commands: list[str] = Field(min_length=1)
    env: dict[str, str] = Field(default_factory=dict)
    timeout_s: int = Field(default=30, gt=0)

    @field_validator("commands")
    @classmethod
    def _commands_non_blank(cls, value: list[str]) -> list[str]:
        for command in value:
            if not command or not command.strip():
                raise ValueError("reproduction commands must be non-empty")
        return value


class ExperimentSpec(UnbodgeModel):
    """One cell of the counterfactual universe.

    The ``cell`` must agree with ``(dependency_version, workaround_state)``:
    A=OLD+PRESENT, B=OLD+ABSENT, C=NEW+PRESENT, D=NEW+ABSENT.
    """

    id: str = Field(min_length=1)
    plan_id: str | None = None
    cell: UniverseCell
    dependency_version: DependencyVersion
    workaround_state: WorkaroundState
    command: str = Field(min_length=1)
    env: dict[str, str] = Field(default_factory=dict)
    timeout_s: int = Field(default=30, gt=0)
    git_sha: str | None = Field(default=None, pattern=_SHA40)
    dependency_state: dict[str, str] = Field(default_factory=dict)

    @field_validator("command")
    @classmethod
    def _command_non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("experiment command must be non-empty")
        return value

    @model_validator(mode="after")
    def _cell_matches_conditions(self) -> ExperimentSpec:
        expected = UniverseCell.for_conditions(self.dependency_version, self.workaround_state)
        if self.cell != expected:
            raise ValueError(
                f"cell {self.cell} contradicts "
                f"({self.dependency_version}, {self.workaround_state}); expected {expected}"
            )
        return self


class ExperimentRun(UnbodgeModel):
    """Recorded outcome of executing one :class:`ExperimentSpec`."""

    id: str = Field(min_length=1)
    spec_id: str = Field(min_length=1)
    cell: UniverseCell
    command: str = Field(min_length=1)
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration_s: float = Field(ge=0.0)
    status: TestStatus
    environment: dict[str, str] = Field(default_factory=dict)
    git_sha: str = Field(pattern=_SHA40)
    dependency_state: dict[str, str] = Field(default_factory=dict)
    test_report: dict[str, Any] = Field(default_factory=dict)
    diff: str = ""
    artifact_hashes: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _status_matches_exit_code(self) -> ExperimentRun:
        if self.status == TestStatus.PASS and self.exit_code != 0:
            raise ValueError("PASS requires exit_code == 0")
        if self.status == TestStatus.FAIL and self.exit_code == 0:
            raise ValueError("FAIL requires exit_code != 0")
        return self


class EvidenceItem(BaseModel):
    """Immutable evidence record.

    Instances are frozen: any post-creation mutation attempt raises.
    The ``hash`` is a deterministic SHA-256 over the content/provenance
    (see :mod:`evidence.hashing`); validation recomputes it to detect tampering.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    id: str = Field(min_length=1)
    evidence_type: EvidenceType
    source: str = Field(min_length=1)
    claim: str = Field(min_length=1)
    artifact_ref: str | None = None
    timestamp: datetime = Field(default_factory=utcnow)
    hash: str = Field(pattern=_HASH64)
    experiment_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _experiment_linkage(self) -> EvidenceItem:
        from domain.enums import EXPERIMENT_LINKED_TYPES

        if self.evidence_type in EXPERIMENT_LINKED_TYPES and not self.experiment_id:
            raise ValueError(f"{self.evidence_type} requires experiment_id")
        if self.evidence_type not in EXPERIMENT_LINKED_TYPES and self.experiment_id:
            raise ValueError(f"{self.evidence_type} must not carry experiment_id")
        return self


class EvidenceLink(UnbodgeModel):
    from_id: str = Field(min_length=1)
    to_id: str = Field(min_length=1)
    relation: str = Field(default="supports", min_length=1)


class EvidenceGraph(UnbodgeModel):
    items: list[EvidenceItem] = Field(default_factory=list)
    links: list[EvidenceLink] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_ids(self) -> EvidenceGraph:
        ids = [item.id for item in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError("evidence ids must be unique")
        return self

    def get(self, item_id: str) -> EvidenceItem | None:
        for item in self.items:
            if item.id == item_id:
                return item
        return None


class RegressionResult(UnbodgeModel):
    id: str = Field(min_length=1)
    suite: str = Field(min_length=1)
    cell: UniverseCell = UniverseCell.D
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    status: TestStatus
    duration_s: float = Field(ge=0.0)
    git_sha: str | None = Field(default=None, pattern=_SHA40)

    @model_validator(mode="after")
    def _status_consistent(self) -> RegressionResult:
        expected = (
            TestStatus.PASS if (self.failed == 0 and self.passed > 0) else TestStatus.FAIL
        )
        if self.status != expected:
            raise ValueError(f"status {self.status} contradicts passed/failed counts")
        return self


class RemovalDecision(UnbodgeModel):
    """Policy outcome. PROPOSE_REMOVAL must cite supporting evidence."""

    id: str = Field(min_length=1)
    hypothesis_id: str | None = None
    outcome: DecisionOutcome
    policy_mode: PolicyMode
    rationale: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def _proposal_cites_evidence(self) -> RemovalDecision:
        if self.outcome == DecisionOutcome.PROPOSE_REMOVAL and not self.evidence_ids:
            raise ValueError("PROPOSE_REMOVAL requires at least one evidence id")
        return self


class PullRequestResult(UnbodgeModel):
    id: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    body: str = ""
    branch: str = Field(min_length=1)
    base: str = "main"
    url: str | None = Field(default=None, pattern=r"^https?://\S+$")
    created_at: datetime = Field(default_factory=utcnow)


class HumanReview(UnbodgeModel):
    id: str = Field(min_length=1)
    decision_id: str | None = None
    reviewer: str = Field(min_length=1)
    verdict: ReviewVerdict
    comment: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class WorkflowTransitionRecord(UnbodgeModel):
    from_state: WorkflowState
    to_state: WorkflowState
    at: datetime = Field(default_factory=utcnow)


class WorkflowRun(UnbodgeModel):
    id: str = Field(min_length=1)
    hypothesis_id: str | None = None
    state: WorkflowState = WorkflowState.DISCOVERED
    history: list[WorkflowTransitionRecord] = Field(default_factory=list)

    def advance(self, to_state: WorkflowState) -> WorkflowRun:
        """Move to ``to_state`` iff the edge is explicitly allowed."""
        transition(self.state, to_state)
        self.history.append(
            WorkflowTransitionRecord(from_state=self.state, to_state=to_state)
        )
        self.state = to_state
        return self