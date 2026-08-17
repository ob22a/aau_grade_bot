"""Shared application service ports for cache, lock, metrics, and time."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable


@runtime_checkable
class CachePort(Protocol):
    async def get(self, key: str) -> str | None:
        ...

    async def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        ...

    async def delete(self, key: str) -> None:
        ...


@runtime_checkable
class DistributedLockPort(Protocol):
    async def acquire(self, key: str, ttl_seconds: int) -> bool:
        ...

    async def release(self, key: str) -> None:
        ...


@runtime_checkable
class ClockPort(Protocol):
    def now_utc(self):
        ...


@runtime_checkable
class MetricsRecorderPort(Protocol):
    async def increment(self, metric: str, value: int = 1) -> None:
        ...

    async def observe(self, metric: str, value: float) -> None:
        ...
