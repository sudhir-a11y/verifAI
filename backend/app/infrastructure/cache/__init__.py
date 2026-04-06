"""In-memory cache layer.

Provides a TTL-based cache abstraction. Falls back to in-memory dict storage
since the application does not currently use Redis or an external cache.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from app.core.config import settings


class InMemoryCache:
    """Thread-safe in-memory cache with TTL support."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        """Get a cached value. Returns None if missing or expired."""
        with self._lock:
            if key not in self._store:
                return None
            value, expires_at = self._store[key]
            if time.monotonic() > expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl_seconds: float = 300) -> None:
        """Set a cache value with TTL."""
        with self._lock:
            self._store[key] = (value, time.monotonic() + ttl_seconds)

    def delete(self, key: str) -> bool:
        """Delete a cache key. Returns True if it existed."""
        with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    def invalidate_prefix(self, prefix: str) -> int:
        """Delete all keys starting with a prefix. Returns count deleted."""
        with self._lock:
            to_delete = [k for k in self._store if k.startswith(prefix)]
            for k in to_delete:
                del self._store[k]
            return len(to_delete)

    def clear(self) -> int:
        """Clear all cache entries. Returns count cleared."""
        with self._lock:
            count = len(self._store)
            self._store.clear()
            return count


# Global cache instance
cache = InMemoryCache()


def get_cache() -> InMemoryCache:
    """Get the global cache instance."""
    return cache


def cache_ttl() -> float:
    """Get the default TTL from settings (falls back to 120s)."""
    return float(getattr(settings, "cache_ttl_seconds", 120))
