"""Durable store contracts (Phase 4).

The domain models remain authoritative: stores persist plain JSON-able
records and never duplicate business logic. Two backends: in-memory
(default, tests) and PostgreSQL (integration, requires a live server).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from domain.errors import UnbodgeError


class StoreError(UnbodgeError):
    """Persistence failure (connection, constraint, serialization)."""


class StoreUnavailableError(StoreError):
    """Backend unreachable or driver missing (explicit, never faked)."""


# Entity tables persisted by the store. Each record is a JSON-able dict
# keyed by its domain-model id.
ENTITIES: tuple[str, ...] = (
    "repositories",
    "upstream_events",
    "issues",
    "fixes",
    "releases",
    "workaround_candidates",
    "causal_hypotheses",
    "reproduction_plans",
    "experiments",
    "experiment_runs",
    "evidence",
    "evidence_links",
    "regression_results",
    "decisions",
    "pr_results",
    "human_reviews",
    "benchmark_cases",
)


class Store(ABC):
    """Key-value record store over the UNBODGE entity tables."""

    @abstractmethod
    def put(self, entity: str, record_id: str, record: dict[str, Any]) -> None:
        """Upsert one record (idempotent by natural key)."""
        ...

    @abstractmethod
    def get(self, entity: str, record_id: str) -> dict[str, Any] | None:
        ...

    @abstractmethod
    def list(self, entity: str, *, limit: int = 100) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def delete(self, entity: str, record_id: str) -> bool:
        ...


def check_entity(entity: str) -> str:
    if entity not in ENTITIES:
        raise StoreError(f"unknown entity table: {entity!r}")
    return entity


__all__ = ["ENTITIES", "Store", "StoreError", "StoreUnavailableError", "check_entity"]
