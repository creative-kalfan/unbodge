"""Transient coordination contracts (Phase 4).

Redis is for locks, cache, rate limiting, and short-lived state ONLY.
It is never the source of truth (see ``packages/persistence``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.errors import UnbodgeError


class CacheError(UnbodgeError):
    """Transient coordination failure."""


class CacheUnavailableError(CacheError):
    """Backend unreachable or driver missing (explicit, never faked)."""


class Cache(ABC):
    """Ephemeral key-value + locking + rate limiting."""

    @abstractmethod
    def get(self, key: str) -> str | None: ...
    @abstractmethod
    def set(self, key: str, value: str, ttl_s: int = 300) -> None: ...
    @abstractmethod
    def delete(self, key: str) -> bool: ...
    @abstractmethod
    def acquire_lock(self, key: str, ttl_s: int = 30) -> bool:
        """Best-effort non-blocking lock; True iff acquired."""
        ...
    @abstractmethod
    def release_lock(self, key: str) -> None: ...
    @abstractmethod
    def allow(self, key: str, limit: int, window_s: int) -> bool:
        """Fixed-window rate limit; True iff the call is allowed."""
        ...


__all__ = ["Cache", "CacheError", "CacheUnavailableError"]
