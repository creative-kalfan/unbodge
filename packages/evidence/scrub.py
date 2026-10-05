"""Deterministic secret redaction for public evidence (Phase 4).

Raw ``EvidenceItem`` records are immutable and never altered. This module
produces a sanitized PUBLIC representation alongside the raw record:

  raw (restricted store)  ->  ScrubbedEvidence (public views, API, UI)

The scrubbed copy keeps the original content ``hash`` so anyone can verify
it binds to the raw record, plus a ``redactions`` count. Deterministic:
same input always yields the same output.
"""

from __future__ import annotations

import re
from datetime import datetime

from domain.enums import EvidenceType
from domain.models import EvidenceItem, UnbodgeModel, utcnow
from pydantic import Field

REDACTED = "[redacted]"

_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ASIA[0-9A-Z]{16}"),
    re.compile(r"ABIA[0-9A-Z]{16}"),
    re.compile(r"ACCA[0-9A-Z]{16}"),
    re.compile(r"ghp_[A-Za-z0-9]{10,}"),
    re.compile(r"gho_[A-Za-z0-9]{10,}"),
    re.compile(r"ghs_[A-Za-z0-9]{10,}"),
    re.compile(r"ghu_[A-Za-z0-9]{10,}"),
    re.compile(r"ghr_[A-Za-z0-9]{10,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]+"),
    re.compile(r"glpat-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"sk-ant-[A-Za-z0-9\-]{16,}"),
    re.compile(r"sk-proj-[A-Za-z0-9\-]{10,}"),
    re.compile(r"sk_live_[A-Za-z0-9]{10,}"),
    re.compile(r"sk_test_[A-Za-z0-9]{10,}"),
    re.compile(r"sk-(live|test)-[A-Za-z0-9]+"),
    re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"),
    re.compile(r"xox[bap]-" + r"[A-Za-z0-9-]+"),
    re.compile(r"xox[oar]-" + r"[A-Za-z0-9-]+"),
    re.compile(r"xox[scde]-" + r"[A-Za-z0-9-]+"),
    re.compile(r"AIza[0-9A-Za-z\-_]{20,}"),
    re.compile(r"\beyJ[A-Za-z0-9\-_]+\.eyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9\-._~+/=]{8,}"),
    re.compile(r"(?i)[\"']?[\w-]*(password|passwd|secret|token|api[_-]?key)[\w-]*[\"']?\s*[:=]\s*\S+"),
    re.compile(r"\b([A-Z][A-Z0-9_]{2,}(?:KEY|TOKEN|SECRET|PASSWORD|PRIVATE))\s*=\s*\S+"),
)


def scrub_text(text: str) -> tuple[str, int]:
    """Redact secret-looking content. Returns ``(cleaned, count)``."""
    if not isinstance(text, str):
        return text, 0
    count = 0
    cleaned = text
    for pattern in _PATTERNS:
        cleaned, found = pattern.subn(REDACTED, cleaned)
        count += found
    return cleaned, count


def _scrub_value(value: object) -> tuple[object, int]:
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, dict):
        total = 0
        out: dict = {}
        for key, item in value.items():
            cleaned_key, key_found = scrub_text(str(key))
            cleaned, found = _scrub_value(item)
            total += key_found + found
            out[cleaned_key] = cleaned
        return out, total
    if isinstance(value, (list, tuple)):
        total = 0
        out_list = []
        for item in value:
            cleaned, found = _scrub_value(item)
            total += found
            out_list.append(cleaned)
        return out_list, total
    return value, 0


class ScrubbedEvidence(UnbodgeModel):
    evidence_id: str = Field(min_length=1)
    evidence_type: EvidenceType
    source: str = Field(min_length=1)
    claim: str = Field(min_length=1)
    artifact_ref: str | None = None
    timestamp: datetime = Field(default_factory=utcnow)
    hash: str = Field(min_length=1)
    experiment_id: str | None = None
    payload: dict = Field(default_factory=dict)
    redactions: int = Field(ge=0)


def scrub_item(item: EvidenceItem) -> ScrubbedEvidence:
    """Build the public sanitized representation of a raw evidence item."""
    total = 0
    claim, found = scrub_text(item.claim)
    total += found
    artifact_ref, found = scrub_text(item.artifact_ref or "")
    total += found
    payload, found = _scrub_value(dict(item.payload))
    total += found
    source, found = scrub_text(item.source)
    total += found
    return ScrubbedEvidence(
        evidence_id=item.id,
        evidence_type=item.evidence_type,
        source=source,
        claim=claim,
        artifact_ref=artifact_ref or None,
        timestamp=item.timestamp,
        hash=item.hash,
        experiment_id=item.experiment_id,
        payload=payload if isinstance(payload, dict) else {},
        redactions=total,
    )


__all__ = ["REDACTED", "ScrubbedEvidence", "scrub_item", "scrub_text"]
