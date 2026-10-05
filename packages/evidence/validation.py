"""Deterministic evidence validation (Phase 1). No LLM involved.

Invalid evidence includes: missing required provenance, malformed hash,
tampered content (recomputed hash mismatch), missing experiment linkage for
experiment evidence, impossible/inconsistent experiment results, and missing
required execution metadata.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from domain.enums import EXPERIMENT_LINKED_TYPES, EvidenceType, TestStatus
from domain.models import EvidenceItem
from evidence.errors import InvalidEvidenceError
from evidence.hashing import evidence_content_hash

_HASH64_RE = re.compile(r"^[0-9a-f]{64}$")

#: Execution metadata required on every EXPERIMENT_RESULT payload.
EXPERIMENT_METADATA_KEYS = (
    "command",
    "stdout",
    "stderr",
    "exit_code",
    "duration_s",
    "environment",
    "git_sha",
    "dependency_state",
    "status",
)

#: Metadata required on every TEST_RESULT payload.
TEST_METADATA_KEYS = ("suite", "passed", "failed", "status")

#: Evidence timestamps more than this far in the future are impossible.
MAX_FUTURE_SKEW_S = 24 * 3600


@dataclass(frozen=True)
class ValidationReport:
    item_id: str
    valid: bool
    errors: tuple[str, ...] = field(default_factory=tuple)


def validate_item(
    item: EvidenceItem, *, now: datetime | None = None
) -> ValidationReport:
    errors: list[str] = []
    moment = now or datetime.now(timezone.utc)

    if not item.source or not item.source.strip():
        errors.append("missing source provenance")
    if not item.claim or not item.claim.strip():
        errors.append("missing claim")

    if not _HASH64_RE.match(item.hash):
        errors.append("malformed hash: must be 64 lowercase hex chars")
    else:
        recomputed = evidence_content_hash(
            evidence_type=item.evidence_type.value,
            source=item.source,
            claim=item.claim,
            artifact_ref=item.artifact_ref,
            timestamp_iso=item.timestamp.isoformat(),
            experiment_id=item.experiment_id,
            payload=item.payload,
        )
        if recomputed != item.hash:
            errors.append("hash mismatch: content does not match provenance hash")

    if item.evidence_type in EXPERIMENT_LINKED_TYPES and not item.experiment_id:
        errors.append(f"{item.evidence_type.value} requires experiment_id")
    if item.evidence_type not in EXPERIMENT_LINKED_TYPES and item.experiment_id:
        errors.append(f"{item.evidence_type.value} must not carry experiment_id")

    if item.timestamp.tzinfo is None:
        errors.append("timestamp must be timezone-aware")
    else:
        skew = (item.timestamp - moment).total_seconds()
        if skew > MAX_FUTURE_SKEW_S:
            errors.append("timestamp is impossibly far in the future")

    if item.evidence_type == EvidenceType.EXPERIMENT_RESULT:
        errors.extend(_check_experiment_metadata(item.payload))
    elif item.evidence_type == EvidenceType.TEST_RESULT:
        errors.extend(_check_test_metadata(item.payload))

    return ValidationReport(item_id=item.id, valid=not errors, errors=tuple(errors))


def _check_experiment_metadata(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in EXPERIMENT_METADATA_KEYS:
        if key not in payload:
            errors.append(f"missing required execution metadata: {key!r}")
    if errors:
        return errors
    for key in ("command", "stdout", "stderr"):
        if not isinstance(payload[key], str):
            errors.append(f"execution metadata {key} must be a string")
    if errors:
        return errors
    exit_code = payload["exit_code"]
    status = payload["status"]
    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
        errors.append("execution metadata exit_code must be an int")
    elif (status == TestStatus.PASS.value and exit_code != 0) or (
        status == TestStatus.FAIL.value and exit_code == 0
    ):
        errors.append("inconsistent experiment result: status contradicts exit_code")
    if status not in (TestStatus.PASS.value, TestStatus.FAIL.value):
        errors.append("execution metadata status must be PASS or FAIL")
    duration = payload["duration_s"]
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration < 0:
        errors.append("execution metadata duration_s must be a non-negative number")
    if not isinstance(payload["environment"], dict):
        errors.append("execution metadata environment must be a mapping")
    if not isinstance(payload["dependency_state"], dict):
        errors.append("execution metadata dependency_state must be a mapping")
    git_sha = payload["git_sha"]
    if not isinstance(git_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", git_sha):
        errors.append("execution metadata git_sha must be a 40-char hex sha")
    return errors


def _check_test_metadata(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in TEST_METADATA_KEYS:
        if key not in payload:
            errors.append(f"missing required test metadata: {key!r}")
    if errors:
        return errors
    if not isinstance(payload["suite"], str):
        errors.append("test metadata suite must be a string")
        return errors
    passed, failed = payload["passed"], payload["failed"]
    if (
        isinstance(passed, bool)
        or isinstance(failed, bool)
        or not isinstance(passed, int)
        or not isinstance(failed, int)
        or passed < 0
        or failed < 0
    ):
        errors.append("test metadata passed/failed must be non-negative ints")
        return errors
    expected = TestStatus.PASS.value if (failed == 0 and passed > 0) else TestStatus.FAIL.value
    if payload["status"] != expected:
        errors.append("inconsistent test result: status contradicts passed/failed counts")
    return errors


def ensure_valid(item: EvidenceItem, *, now: datetime | None = None) -> EvidenceItem:
    report = validate_item(item, now=now)
    if not report.valid:
        raise InvalidEvidenceError(item.id, list(report.errors))
    return item