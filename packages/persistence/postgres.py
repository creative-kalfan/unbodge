"""PostgreSQL store (Phase 4).

Real persistence against a live PostgreSQL server (psycopg2). No server
=> explicit ``StoreUnavailableError`` (integration tests skip). The
driver import is lazy so offline environments import this module safely.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

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


def _parse_dsn(dsn: str) -> dict[str, Any]:
    """Parse DSN into psycopg2 connect keyword arguments, supporting both URL and key=value formats."""
    if "://" in dsn:
        u = urlparse(dsn)
        kwargs: dict[str, Any] = {}
        if u.username is not None:
            kwargs["user"] = unquote(u.username)
        if u.password is not None:
            kwargs["password"] = unquote(u.password)
        if u.hostname is not None:
            kwargs["host"] = u.hostname
        if u.port is not None:
            kwargs["port"] = u.port
        db = u.path.lstrip("/")
        if db:
            kwargs["dbname"] = db
        if u.query:
            qs = parse_qs(u.query)
            for k, vs in qs.items():
                if vs:
                    kwargs[k] = vs[-1]
        return kwargs
    return {"dsn": dsn}


class PostgresStore(Store):
    """JSONB record store. ``dsn`` e.g. ``dbname=unbodge user=postgres`` or URL."""

    def __init__(self, dsn: str, *, ensure_schema: bool = True) -> None:
        if not dsn.strip():
            raise ValueError("dsn must be non-empty")
        self._dsn = dsn
        conn_kwargs = _parse_dsn(dsn)
        if "connect_timeout" not in conn_kwargs and "connect_timeout" not in dsn:
            conn_kwargs["connect_timeout"] = 5
        try:
            self._conn = _driver().connect(**conn_kwargs)
            self._conn.autocommit = True
        except Exception as exc:
            raise StoreUnavailableError(f"postgres unreachable: {_redact(exc)}") from exc
        if ensure_schema:
            try:
                with self._conn.cursor() as cur:
                    cur.execute(_load_schema())
            except Exception as exc:
                raise StoreError(f"schema setup failed: {_redact(exc)}") from exc

    def ping(self) -> bool:
        """Safe non-destructive health check (SELECT 1)."""
        try:
            with self._conn.cursor() as cur:
                cur.execute("SELECT 1")
                row = cur.fetchone()
                return bool(row and row[0] == 1)
        except Exception:
            return False

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
    text = str(error)
    text = re.sub(r"password=[^\s]+", "password=[redacted]", text)
    text = re.sub(r"://([^:]+):([^@]+)@", r"://\1:[redacted]@", text)
    return text[:300]


__all__ = ["PostgresStore"]
