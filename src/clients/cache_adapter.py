"""In-memory cache adapter for CachePort."""

from __future__ import annotations

import time
from typing import Dict, Tuple


class InMemoryCache:
    """A simple in-memory cache implementing CachePort."""

    def __init__(self) -> None:
        # key -> (value, expires_at_timestamp)
        self._store: Dict[str, Tuple[str, float | None]] = {}

    async def get(self, key: str) -> str | None:
        if key not in self._store:
            return None
        value, expires_at = self._store[key]
        if expires_at is not None and time.time() > expires_at:
            del self._store[key]
            return None
        return value

    async def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        expires_at = time.time() + ttl_seconds if ttl_seconds is not None else None
        self._store[key] = (value, expires_at)

    async def delete(self, key: str) -> None:
        if key in self._store:
            del self._store[key]
