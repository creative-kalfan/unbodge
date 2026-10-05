"""Proof-chain evidence graph construction (Phase 2).

Assembles the explicit link chain:

upstream issue -> fix commit -> release -> dependency state
-> workaround reference -> experiment -> experiment result
-> regression result -> policy decision

All nodes must already be validated ``EvidenceItem``s; the builder only
wires typed links and validates the resulting graph. Prose and model
confidence never enter: every node carries a content hash.
"""

from __future__ import annotations

from collections.abc import Sequence

from domain.models import EvidenceGraph, EvidenceItem, EvidenceLink, ExperimentRun
from evidence.graph import GraphValidationReport, validate_graph


def run_payload(run: ExperimentRun) -> dict:
    """Build the ``EXPERIMENT_RESULT`` payload dict from a real run."""
    return {
        "command": run.command,
        "stdout": run.stdout,
        "stderr": run.stderr,
        "exit_code": run.exit_code,
        "duration_s": run.duration_s,
        "environment": dict(run.environment),
        "git_sha": run.git_sha,
        "dependency_state": dict(run.dependency_state),
        "status": run.status.value,
        "test_report": dict(run.test_report),
        "artifact_hashes": dict(run.artifact_hashes),
    }

#: Canonical relation names for the proof chain, in order.
CHAIN_RELATIONS: tuple[str, ...] = (
    "documents",
    "fixed-by",
    "released-in",
    "pins",
    "compensates",
    "executed-as",
    "resulted-in",
    "regression-checked-by",
    "decided-by",
    "superseded-by",
)


def build_proof_graph(
    items: Sequence[EvidenceItem],
    links: Sequence[tuple[str, str, str]],
) -> EvidenceGraph:
    """Wire ``(from_id, to_id, relation)`` links over validated items."""
    return EvidenceGraph(
        items=list(items),
        links=[EvidenceLink(from_id=a, to_id=b, relation=r) for a, b, r in links],
    )


def build_chain_graph(
    items: Sequence[EvidenceItem], relations: Sequence[str] | None = None
) -> EvidenceGraph:
    """Link ``items`` in order with the canonical chain relations.

    Requires at least two items. ``relations`` overrides the positional
    defaults (extra items beyond the relations use ``"supports"``).
    """
    ordered = list(items)
    if len(ordered) < 2:
        raise ValueError("a proof chain needs at least two evidence items")
    names = list(relations) if relations is not None else list(CHAIN_RELATIONS)
    links: list[tuple[str, str, str]] = []
    for index in range(len(ordered) - 1):
        relation = names[index] if index < len(names) else "supports"
        links.append((ordered[index].id, ordered[index + 1].id, relation))
    return build_proof_graph(ordered, links)


def check_chain(
    graph: EvidenceGraph,
) -> GraphValidationReport:
    """Validate the graph (items, links, acyclicity)."""
    return validate_graph(graph)


__all__ = [
    "CHAIN_RELATIONS",
    "build_chain_graph",
    "build_proof_graph",
    "check_chain",
    "run_payload",
]
