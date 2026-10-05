"""Structured evidence records, hashing, validation and graph (Phase 1)."""
from evidence.chain import (
    CHAIN_RELATIONS,
    build_chain_graph,
    build_proof_graph,
    check_chain,
)
from evidence.errors import EvidenceError, InvalidEvidenceError
from evidence.graph import check_acyclic, validate_graph
from evidence.hashing import canonical_json, evidence_content_hash, sha256_hex
from evidence.items import make_evidence
from evidence.scrub import REDACTED, ScrubbedEvidence, scrub_item, scrub_text
from evidence.validation import ValidationReport, ensure_valid, validate_item

__all__ = [
    "CHAIN_RELATIONS",
    "EvidenceError",
    "InvalidEvidenceError",
    "REDACTED",
    "ScrubbedEvidence",
    "ValidationReport",
    "build_chain_graph",
    "build_proof_graph",
    "canonical_json",
    "check_acyclic",
    "check_chain",
    "ensure_valid",
    "evidence_content_hash",
    "make_evidence",
    "scrub_item",
    "scrub_text",
    "sha256_hex",
    "validate_graph",
    "validate_item",
]