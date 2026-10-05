"""Redis transient coordination (Phase 4).

Real Redis via ``redis-py`` when installed AND reachable; otherwise
explicit ``CacheUnavailableError`` (integration tests skip). The driver
import is lazy so offline environments import safely.
"""

from __future__ import annotations

import time
import uuid

from cache.base import Cache, CacheError, CacheUnavailableError


def _driver():
    try:
        import redis
    except ImportError as exc:
        raise CacheUnavailableError("redis-py is not installed") from exc
    return redis


class RedisCache(Cache):
    def __init__(self, url: str = "redis://localhost:6379/0", *, namespace: str = "unbodge:") -> None:
        if not url.strip():
            raise ValueError("url must be non-empty")
        module = _driver()
        try:
            self._client = module.Redis.from_url(url, socket_timeout=5)
            self._client.ping()
        except Exception as exc:
            raise CacheUnavailableError(f"redis unreachable: {exc}") from exc
        self._namespace = namespace
        self._tokens: dict[str, str] = {}

    def _key(self, key: str) -> str:
        if not key or len(key) > 512:
            raise CacheError("invalid cache key")
        return f"{self._namespace}{key}"

    def get(self, key: str) -> str | None:
        try:
            value = self._client.get(self._key(key))
            if isinstance(value, bytes):
                return value.decode("utf-8")
            return value
        except UnicodeDecodeError as exc:
            raise CacheError(f"redis value not decodable: {exc}") from exc
        except Exception as exc:
            raise CacheError(f"redis get failed: {exc}") from exc

    def set(self, key: str, value: str, ttl_s: int = 300) -> None:
        if ttl_s <= 0:
            raise ValueError("ttl_s must be positive")
        try:
            self._client.set(self._key(key), value, ex=ttl_s)
        except Exception as exc:
            raise CacheError(f"redis set failed: {exc}") from exc

    def delete(self, key: str) -> bool:
        try:
            return bool(self._client.delete(self._key(key)))
        except Exception as exc:
            raise CacheError(f"redis delete failed: {exc}") from exc

    def acquire_lock(self, key: str, ttl_s: int = 30) -> bool:
        token = uuid.uuid4().hex
        try:
            acquired = self._client.set(self._key(f"lock:{key}"), token, ex=ttl_s, nx=True)
        except Exception as exc:
            raise CacheError(f"redis lock failed: {exc}") from exc
        if acquired:
            self._tokens[key] = token
            return True
        return False

    def release_lock(self, key: str) -> None:
        # Best-effort, single-process oriented: only the holder that still
        # has its token can release. Not for correctness-critical exclusion
        # across processes (locks expire via TTL instead).
        token = self._tokens.pop(key, None)
        if token is None:
            return
        script = (
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('del', KEYS[1]) else return 0 end"
        )
        try:
            self._client.eval(script, 1, self._key(f"lock:{key}"), token)
        except Exception as exc:
            raise CacheError(f"redis unlock failed: {exc}") from exc

    def allow(self, key: str, limit: int, window_s: int) -> bool:
        if limit < 1 or window_s < 1:
            raise ValueError("limit and window_s must be positive")
        member = f"{time.time_ns()}:{uuid.uuid4().hex}"
        now = time.time()
        redis_key = self._key(f"ratelimit:{key}")
        script = (
            "redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, ARGV[1]) "
            "local count = redis.call('ZCARD', KEYS[1]) "
            "if count >= tonumber(ARGV[2]) then return 0 end "
            "redis.call('ZADD', KEYS[1], ARGV[3], ARGV[4]) "
            "redis.call('EXPIRE', KEYS[1], ARGV[5]) "
            "return 1"
        )
        try:
            allowed = self._client.eval(
                script, 1, redis_key, now, now - window_s, limit, now, member, window_s + 1
            )
        except Exception as exc:
            raise CacheError(f"redis rate limit failed: {exc}") from exc
        return bool(allowed)


__all__ = ["RedisCache"]
