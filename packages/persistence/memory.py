"""In-memory store (Phase 4 default). Deterministic, offline, test-friendly."""

from __future__ import annotations

import copy
from typing import Any

from persistence.base import ENTITIES, Store, check_entity


class MemoryStore(Store):
    def __init__(self) -> None:
        self._tables: dict[str, dict[str, dict[str, Any]]] = {
            entity: {} for entity in ENTITIES
        }

    def put(self, entity: str, record_id: str, record: dict[str, Any]) -> None:
        check_entity(entity)
        if not record_id:
            raise ValueError("record_id must be non-empty")
        self._tables[entity][record_id] = copy.deepcopy(record)

    def get(self, entity: str, record_id: str) -> dict[str, Any] | None:
        check_entity(entity)
        record = self._tables[entity].get(record_id)
        return copy.deepcopy(record) if record is not None else None

    def list(self, entity: str, *, limit: int = 100) -> list[dict[str, Any]]:
        check_entity(entity)
        if limit < 1:
            raise ValueError("limit must be positive")
        return copy.deepcopy(list(self._tables[entity].values())[:limit])

    def delete(self, entity: str, record_id: str) -> bool:
        check_entity(entity)
        return self._tables[entity].pop(record_id, None) is not None


__all__ = ["MemoryStore"]
