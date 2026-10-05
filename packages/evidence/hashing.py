"""Deterministic content/provenance hashing for evidence (Phase 1).

No cryptography theatre: SHA-256 over a canonical JSON encoding of the
content + provenance fields. Deterministic across runs and machines
(``sort_keys``, fixed separators, UTC ISO timestamps).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def _reject_non_json_native(value: Any) -> Any:
    raise TypeError(
        f"non-JSON-native type in evidence content: {type(value).__name__}"
    )


def canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=_reject_non_json_native,
    )


def sha256_hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def evidence_content_hash(
    *,
    evidence_type: str,
    source: str,
    claim: str,
    artifact_ref: str | None,
    timestamp_iso: str,
    experiment_id: str | None,
    payload: Mapping[str, Any],
) -> str:
    canonical = canonical_json(
        {
            "artifact_ref": artifact_ref,
            "claim": claim,
            "evidence_type": evidence_type,
            "experiment_id": experiment_id,
            "payload": dict(payload),
            "source": source,
            "timestamp": timestamp_iso,
        }
    )
    return sha256_hex(canonical)