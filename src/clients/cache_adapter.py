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

    async def acquire_lock(self, key: str, ttl_seconds: int = 30) -> bool:
        if key in self._store:
            _, expires_at = self._store[key]
            if expires_at is None or time.time() < expires_at:
                return False
        # Acquire
        self._store[key] = ("1", time.time() + ttl_seconds)
        return True

    async def release_lock(self, key: str) -> None:
        await self.delete(key)

class RedisCache:
    """Redis-backed cache adapter."""

    def __init__(self, url: str) -> None:
        import redis.asyncio as redis
        self.redis = redis.from_url(url, decode_responses=True)

    async def get(self, key: str) -> str | None:
        try:
            return await self.redis.get(key)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Redis get error: {e}")
            return None

    async def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        try:
            if ttl_seconds is not None:
                await self.redis.setex(key, ttl_seconds, value)
            else:
                await self.redis.set(key, value)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Redis set error: {e}")

    async def delete(self, key: str) -> None:
        try:
            await self.redis.delete(key)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Redis delete error: {e}")

    async def acquire_lock(self, key: str, ttl_seconds: int = 30) -> bool:
        try:
            return await self.redis.set(key, "1", nx=True, ex=ttl_seconds)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Redis acquire_lock error: {e}")
            return True # If Redis fails, allow the scrape to proceed as a fallback

    async def release_lock(self, key: str) -> None:
        try:
            await self.redis.delete(key)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Redis release_lock error: {e}")
