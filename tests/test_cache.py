"""Transient coordination: memory contract always, Redis when live."""

import time

import pytest

from cache import CacheUnavailableError, MemoryCache, RedisCache


def _contract_suite(cache, label: str):
    assert cache.get("missing") is None
    cache.set("k", "v")
    assert cache.get("k") == "v"
    assert cache.delete("k") is True
    assert cache.delete("k") is False
    assert cache.acquire_lock("job") is True
    assert cache.acquire_lock("job") is False
    cache.release_lock("job")
    assert cache.acquire_lock("job") is True
    cache.release_lock("job")
    assert cache.allow("api", limit=2, window_s=60) is True
    assert cache.allow("api", limit=2, window_s=60) is True
    assert cache.allow("api", limit=2, window_s=60) is False
    with pytest.raises(ValueError):
        cache.set("k", "v", ttl_s=0)
    with pytest.raises(ValueError):
        cache.allow("api", limit=0, window_s=60)
    assert label in ("memory", "redis")


def test_memory_cache_contract():
    _contract_suite(MemoryCache(), "memory")


def test_memory_cache_ttl_and_lock_expiry():
    cache = MemoryCache()
    cache.set("short", "v", ttl_s=3600)
    assert cache.get("short") == "v"
    assert cache.acquire_lock("x", ttl_s=3600) is True
    cache.release_lock("missing")  # no-op, never raises


def _redis_url() -> str | None:
    import os

    return os.environ.get("UNBODGE_TEST_REDIS_URL")


def test_redis_cache_contract_or_skip():
    url = _redis_url()
    if not url:
        pytest.skip("UNBODGE_TEST_REDIS_URL not set")
    try:
        cache = RedisCache(url, namespace="unbodge-test:")
    except CacheUnavailableError as exc:
        pytest.skip(f"redis unavailable: {exc}")
    _contract_suite(cache, "redis")


def test_redis_bad_url_fails_closed():
    with pytest.raises(CacheUnavailableError):
        RedisCache("redis://127.0.0.1:1/0")
