"""In-memory transient coordination (Phase 4 default)."""

from __future__ import annotations

import threading
import time

from cache.base import Cache


class MemoryCache(Cache):
    def __init__(self) -> None:
        self._values: dict[str, tuple[str, float]] = {}
        self._locks: dict[str, float] = {}
        self._windows: dict[str, list[float]] = {}
        self._mutex = threading.Lock()

    def _purge(self, now: float) -> None:
        self._values = {k: v for k, v in self._values.items() if v[1] > now}
        self._locks = {k: v for k, v in self._locks.items() if v > now}

    def get(self, key: str) -> str | None:
        with self._mutex:
            now = time.time()
            self._purge(now)
            entry = self._values.get(key)
            return entry[0] if entry is not None else None

    def set(self, key: str, value: str, ttl_s: int = 300) -> None:
        if ttl_s <= 0:
            raise ValueError("ttl_s must be positive")
        with self._mutex:
            self._values[key] = (value, time.time() + ttl_s)

    def delete(self, key: str) -> bool:
        with self._mutex:
            self._purge(time.time())
            return self._values.pop(key, None) is not None

    def acquire_lock(self, key: str, ttl_s: int = 30) -> bool:
        with self._mutex:
            now = time.time()
            self._purge(now)
            if key in self._locks:
                return False
            self._locks[key] = now + ttl_s
            return True

    def release_lock(self, key: str) -> None:
        with self._mutex:
            self._locks.pop(key, None)

    def allow(self, key: str, limit: int, window_s: int) -> bool:
        if limit < 1 or window_s < 1:
            raise ValueError("limit and window_s must be positive")
        with self._mutex:
            now = time.time()
            hits = [t for t in self._windows.get(key, []) if t > now - window_s]
            if len(hits) >= limit:
                self._windows[key] = hits
                return False
            hits.append(now)
            self._windows[key] = hits
            return True


__all__ = ["MemoryCache"]
