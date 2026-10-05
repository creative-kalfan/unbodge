"""Shared domain enumerations for UNBODGE Phase 1.

Centralising enums in the domain package keeps dependencies one-directional:
evidence / experiments / sandbox / policy import from here, never the reverse.
"""
from __future__ import annotations

from enum import Enum


class DependencyVersion(str, Enum):
    OLD = "OLD"
    NEW = "NEW"


class WorkaroundState(str, Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"


class UniverseCell(str, Enum):
    """Counterfactual universe.

    A = OLD + workaround, B = OLD + no workaround,
    C = NEW + workaround, D = NEW + no workaround.
    """

    A = "A"
    B = "B"
    C = "C"
    D = "D"

    @property
    def dependency(self) -> DependencyVersion:
        if self in (UniverseCell.A, UniverseCell.B):
            return DependencyVersion.OLD
        return DependencyVersion.NEW

    @property
    def workaround(self) -> WorkaroundState:
        if self in (UniverseCell.A, UniverseCell.C):
            return WorkaroundState.PRESENT
        return WorkaroundState.ABSENT

    @classmethod
    def for_conditions(
        cls, dependency: DependencyVersion, workaround: WorkaroundState
    ) -> UniverseCell:
        if dependency == DependencyVersion.OLD and workaround == WorkaroundState.PRESENT:
            return cls.A
        if dependency == DependencyVersion.OLD and workaround == WorkaroundState.ABSENT:
            return cls.B
        if dependency == DependencyVersion.NEW and workaround == WorkaroundState.PRESENT:
            return cls.C
        return cls.D


class EvidenceType(str, Enum):
    UPSTREAM_ISSUE = "UPSTREAM_ISSUE"
    FIX_COMMIT = "FIX_COMMIT"
    RELEASE = "RELEASE"
    CODE_REFERENCE = "CODE_REFERENCE"
    DEPENDENCY_STATE = "DEPENDENCY_STATE"
    EXPERIMENT_RESULT = "EXPERIMENT_RESULT"
    TEST_RESULT = "TEST_RESULT"
    SEARCH_RESULT = "SEARCH_RESULT"
    HUMAN_REVIEW = "HUMAN_REVIEW"


#: Evidence types that must carry an experiment linkage.
EXPERIMENT_LINKED_TYPES = frozenset({EvidenceType.EXPERIMENT_RESULT, EvidenceType.TEST_RESULT})


class TestStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


class PolicyMode(str, Enum):
    PROPOSE_ONLY = "PROPOSE_ONLY"
    STRICT_AUTO_MERGE = "STRICT_AUTO_MERGE"
    HUMAN_APPROVAL_REQUIRED = "HUMAN_APPROVAL_REQUIRED"


class DecisionOutcome(str, Enum):
    PROPOSE_REMOVAL = "PROPOSE_REMOVAL"
    ABSTAIN = "ABSTAIN"


class RationaleCode(str, Enum):
    OK_PROPOSE = "OK_PROPOSE"
    EVIDENCE_INVALID = "EVIDENCE_INVALID"
    MATRIX_MISMATCH = "MATRIX_MISMATCH"
    CONTRADICTORY_EVIDENCE = "CONTRADICTORY_EVIDENCE"
    REGRESSION_FAIL = "REGRESSION_FAIL"
    MODE_NOT_ENABLED = "MODE_NOT_ENABLED"
    MISSING_EVIDENCE_REFS = "MISSING_EVIDENCE_REFS"


class IssueState(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class ReviewVerdict(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    NEEDS_MORE_EVIDENCE = "NEEDS_MORE_EVIDENCE"