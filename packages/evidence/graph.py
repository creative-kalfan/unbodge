"""Evidence-graph validation helpers (Phase 1)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from domain.models import EvidenceGraph
from evidence.validation import validate_item


@dataclass(frozen=True)
class GraphValidationReport:
    valid: bool
    errors: tuple[str, ...] = field(default_factory=tuple)


def check_acyclic(graph: EvidenceGraph) -> list[str]:
    """Return error strings if the link structure contains a cycle."""
    adjacency: dict[str, list[str]] = {}
    for link in graph.links:
        adjacency.setdefault(link.from_id, []).append(link.to_id)
    visiting: set[str] = set()
    visited: set[str] = set()
    cycle: list[str] = []

    def visit(node: str, stack: list[str]) -> None:
        if cycle or node in visited:
            return
        if node in visiting:
            cycle.append(f"cycle detected: {' -> '.join([*stack, node])}")
            return
        visiting.add(node)
        for child in adjacency.get(node, []):
            visit(child, [*stack, node])
        visiting.discard(node)
        visited.add(node)

    for link in graph.links:
        visit(link.from_id, [])
    return cycle


def validate_graph(
    graph: EvidenceGraph, *, now: datetime | None = None
) -> GraphValidationReport:
    errors: list[str] = []
    ids = {item.id for item in graph.items}
    for item in graph.items:
        report = validate_item(item, now=now)
        if not report.valid:
            errors.append(f"item {item.id}: {'; '.join(report.errors)}")
    for link in graph.links:
        if link.from_id not in ids:
            errors.append(f"link references unknown evidence: {link.from_id!r}")
        if link.to_id not in ids:
            errors.append(f"link references unknown evidence: {link.to_id!r}")
    errors.extend(check_acyclic(graph))
    return GraphValidationReport(valid=not errors, errors=tuple(errors))