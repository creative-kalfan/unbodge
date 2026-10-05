"""Research-to-evidence bridge (Phase 3).

Converts research results into ``SEARCH_RESULT`` evidence records with
full provenance (query, source URL, retrieval time, content hash).
Validation stays with the evidence engine; research never self-certifies.
"""

from __future__ import annotations

from domain.enums import EvidenceType
from domain.models import EvidenceItem
from evidence.hashing import sha256_hex
from evidence.items import make_evidence
from research.models import ResearchBundle


def research_to_evidence(
    bundle: ResearchBundle, *, claim_prefix: str = "research"
) -> list[EvidenceItem]:
    """Mint one ``SEARCH_RESULT`` item per research result."""
    items: list[EvidenceItem] = []
    for index, result in enumerate(bundle.results):
        content_hash = result.content_hash
        if len(content_hash) != 64:
            content_hash = sha256_hex(
                f"{bundle.query}\n{result.url}\n{result.title}\n{result.snippet}"
            )
        items.append(
            make_evidence(
                id=f"ev:research:{index}:{content_hash[:12]}",
                evidence_type=EvidenceType.SEARCH_RESULT,
                source=result.source or "research",
                claim=f"{claim_prefix}: {result.title or result.url}",
                artifact_ref=result.url,
                timestamp=result.retrieved_at,
                payload={
                    "query": bundle.query,
                    "url": result.url,
                    "content_hash": content_hash,
                },
            )
        )
    return items


__all__ = ["research_to_evidence"]
