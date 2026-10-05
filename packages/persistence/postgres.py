"""PostgreSQL store (Phase 4).

Real persistence against a live PostgreSQL server (psycopg2). No server
=> explicit ``StoreUnavailableError`` (integration tests skip). The
driver import is lazy so offline environments import this module safely.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from persistence.base import Store, StoreError, StoreUnavailableError, check_entity

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def _load_schema() -> str:
    try:
        return _SCHEMA_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise StoreError(f"schema file missing: {exc}") from exc


def _driver():
    try:
        import psycopg2
    except ImportError as exc:
        raise StoreUnavailableError("psycopg2 is not installed") from exc
    return psycopg2


class PostgresStore(Store):
    """JSONB record store. ``dsn`` e.g. ``dbname=unbodge user=postgres``."""

    def __init__(self, dsn: str, *, ensure_schema: bool = True) -> None:
        if not dsn.strip():
            raise ValueError("dsn must be non-empty")
        if "connect_timeout" not in dsn:
            dsn = f"{dsn} connect_timeout=5"
        self._dsn = dsn
        try:
            self._conn = _driver().connect(dsn)
            self._conn.autocommit = True
        except Exception as exc:
            raise StoreUnavailableError(f"postgres unreachable: {_redact(exc)}") from exc
        if ensure_schema:
            try:
                with self._conn.cursor() as cur:
                    cur.execute(_load_schema())
            except Exception as exc:
                raise StoreError(f"schema setup failed: {_redact(exc)}") from exc

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def put(self, entity: str, record_id: str, record: dict[str, Any]) -> None:
        check_entity(entity)
        if not record_id:
            raise ValueError("record_id must be non-empty")
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    f"INSERT INTO {entity} (id, record, updated_at) "
                    "VALUES (%s, %s::jsonb, now()) "
                    "ON CONFLICT (id) DO UPDATE SET record = EXCLUDED.record, "
                    "updated_at = now()",
                    (record_id, json.dumps(record, sort_keys=True, default=str)),
                )
        except Exception as exc:
            raise StoreError(f"put failed: {exc}") from exc

    def get(self, entity: str, record_id: str) -> dict[str, Any] | None:
        check_entity(entity)
        try:
            with self._conn.cursor() as cur:
                cur.execute(f"SELECT record FROM {entity} WHERE id = %s", (record_id,))
                row = cur.fetchone()
            if row is None:
                return None
            record = dict(row[0])
            if not isinstance(record, dict):
                raise StoreError("stored record is not an object")
            return record
        except StoreError:
            raise
        except Exception as exc:
            raise StoreError(f"get failed: {exc}") from exc

    def list(self, entity: str, *, limit: int = 100) -> list[dict[str, Any]]:
        check_entity(entity)
        if limit < 1:
            raise ValueError("limit must be positive")
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    f"SELECT record FROM {entity} ORDER BY id LIMIT %s", (limit,)
                )
                return [dict(row[0]) for row in cur.fetchall()]
        except Exception as exc:
            raise StoreError(f"list failed: {exc}") from exc

    def delete(self, entity: str, record_id: str) -> bool:
        check_entity(entity)
        try:
            with self._conn.cursor() as cur:
                cur.execute(f"DELETE FROM {entity} WHERE id = %s", (record_id,))
                return cur.rowcount > 0
        except Exception as exc:
            raise StoreError(f"delete failed: {exc}") from exc


def _redact(error: Exception) -> str:
    """Strip password material from driver error text."""
    import re

    text = str(error)
    text = re.sub(r"password=[^\s]+", "password=[redacted]", text)
    return text[:300]


__all__ = ["PostgresStore"]
