"""Tests for cloud configuration, persistent adapter wiring, and factory behaviors."""

from __future__ import annotations

import os
import pytest
from starlette.testclient import TestClient

from api.app import create_app
from cache import MemoryCache, RedisCache
from cache.base import CacheUnavailableError
from persistence import MemoryStore, PostgresStore
from persistence.base import StoreUnavailableError
from persistence.postgres import _parse_dsn, _redact as _redact_pg
from cache.redis_backend import _redact as _redact_redis


def test_parse_dsn_kv():
    parsed = _parse_dsn("dbname=unbodge user=postgres host=localhost port=5432")
    assert parsed == {"dsn": "dbname=unbodge user=postgres host=localhost port=5432"}


def test_parse_dsn_url_standard():
    url = "postgresql://myuser:mypassword@db.host.com:5432/proddb?sslmode=require"
    parsed = _parse_dsn(url)
    assert parsed["user"] == "myuser"
    assert parsed["password"] == "mypassword"
    assert parsed["host"] == "db.host.com"
    assert parsed["port"] == 5432
    assert parsed["dbname"] == "proddb"
    assert parsed["sslmode"] == "require"


def test_parse_dsn_url_with_special_characters():
    url = "postgresql://user.suffix:pass%40word@pooler.host.com:5432/postgres?sslmode=require"
    parsed = _parse_dsn(url)
    assert parsed["user"] == "user.suffix"
    assert parsed["password"] == "pass@word"
    assert parsed["host"] == "pooler.host.com"
    assert parsed["port"] == 5432
    assert parsed["dbname"] == "postgres"


def test_redact_pg_removes_secrets():
    err1 = Exception("connection failed: postgresql://admin:supersecret123@host:5432/db")
    assert "supersecret123" not in _redact_pg(err1)
    assert "[redacted]" in _redact_pg(err1)

    err2 = Exception("failed connect dbname=test password=supersecret456 host=remote")
    assert "supersecret456" not in _redact_pg(err2)
    assert "[redacted]" in _redact_pg(err2)


def test_redact_redis_removes_secrets():
    err = Exception("failed connecting to rediss://default:upstashsecret@host.upstash.io:6379")
    assert "upstashsecret" not in _redact_redis(err)
    assert "[redacted]" in _redact_redis(err)


def test_create_app_explicit_di_preserves_memory_mode(monkeypatch):
    monkeypatch.setenv("UNBODGE_POSTGRES_DSN", "postgresql://user:pass@127.0.0.1:1/db")
    monkeypatch.setenv("UNBODGE_REDIS_URL", "redis://user:pass@127.0.0.1:1/0")
    mem_store = MemoryStore()
    mem_cache = MemoryCache()
    app = create_app(store=mem_store, cache=mem_cache)
    assert app.state.store is mem_store
    assert app.state.cache is mem_cache


def test_create_app_defaults_to_memory_when_no_env(monkeypatch):
    monkeypatch.delenv("UNBODGE_POSTGRES_DSN", raising=False)
    monkeypatch.delenv("UNBODGE_REDIS_URL", raising=False)
    app = create_app()
    assert isinstance(app.state.store, MemoryStore)
    assert isinstance(app.state.cache, MemoryCache)


def test_create_app_fails_startup_when_postgres_unreachable(monkeypatch):
    monkeypatch.setenv("UNBODGE_POSTGRES_DSN", "postgresql://user:pass@127.0.0.1:1/db")
    monkeypatch.delenv("UNBODGE_REDIS_URL", raising=False)
    with pytest.raises(StoreUnavailableError):
        create_app()


def test_create_app_fails_startup_when_redis_unreachable(monkeypatch):
    monkeypatch.delenv("UNBODGE_POSTGRES_DSN", raising=False)
    monkeypatch.setenv("UNBODGE_REDIS_URL", "redis://user:pass@127.0.0.1:1/0")
    with pytest.raises(CacheUnavailableError):
        create_app()


def test_app_lifespan_closes_resources():
    class ClosableStore(MemoryStore):
        def __init__(self):
            super().__init__()
            self.closed = False
        def close(self):
            self.closed = True

    class ClosableCache(MemoryCache):
        def __init__(self):
            super().__init__()
            self.closed = False
        def close(self):
            self.closed = True

    store = ClosableStore()
    cache = ClosableCache()
    app = create_app(store=store, cache=cache)
    with TestClient(app):
        assert not store.closed
        assert not cache.closed
    assert store.closed
    assert cache.closed
