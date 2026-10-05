"""Evidence factories (Phase 1).

The only sanctioned way to mint an :class:`EvidenceItem`: the hash is always
computed from the content/provenance, never caller-supplied.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from domain.enums import EvidenceType
from domain.models import EvidenceItem, utcnow
from evidence.hashing import evidence_content_hash


def make_evidence(
    *,
    id: str,
    evidence_type: EvidenceType,
    source: str,
    claim: str,
    artifact_ref: str | None = None,
    experiment_id: str | None = None,
    payload: Mapping[str, Any] | None = None,
    timestamp: datetime | None = None,
) -> EvidenceItem:
    payload_dict = dict(payload) if payload else {}
    moment = timestamp or utcnow()
    if moment.tzinfo is None:
        raise ValueError("evidence timestamp must be timezone-aware")
    digest = evidence_content_hash(
        evidence_type=evidence_type.value,
        source=source,
        claim=claim,
        artifact_ref=artifact_ref,
        timestamp_iso=moment.isoformat(),
        experiment_id=experiment_id,
        payload=payload_dict,
    )
    return EvidenceItem(
        id=id,
        evidence_type=evidence_type,
        source=source,
        claim=claim,
        artifact_ref=artifact_ref,
        timestamp=moment,
        hash=digest,
        experiment_id=experiment_id,
        payload=payload_dict,
    )