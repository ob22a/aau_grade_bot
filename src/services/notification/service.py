"""Notification orchestration service."""

from __future__ import annotations

from typing import Any
import asyncio
import time
from collections import deque

class RateLimiter:
    def __init__(self, global_limit: int = 30, user_limit: int = 1):
        self.global_limit = global_limit
        self.user_limit = user_limit
        self.global_timestamps: deque[float] = deque()
        self.user_timestamps: dict[int, deque[float]] = {}
        self.lock = asyncio.Lock()

    async def acquire(self, user_id: int | None = None) -> None:
        while True:
            async with self.lock:
                now = time.time()
                
                while self.global_timestamps and now - self.global_timestamps[0] >= 1.0:
                    self.global_timestamps.popleft()
                
                if user_id is not None:
                    if user_id not in self.user_timestamps:
                        self.user_timestamps[user_id] = deque()
                    while self.user_timestamps[user_id] and now - self.user_timestamps[user_id][0] >= 1.0:
                        self.user_timestamps[user_id].popleft()

                can_send = True
                if len(self.global_timestamps) >= self.global_limit:
                    can_send = False
                
                if user_id is not None and len(self.user_timestamps[user_id]) >= self.user_limit:
                    can_send = False
                
                if can_send:
                    self.global_timestamps.append(now)
                    if user_id is not None:
                        self.user_timestamps[user_id].append(now)
                    return
            
            await asyncio.sleep(0.05)


class NotificationService:
    def __init__(self, sender: Any | None = None) -> None:
        self.sender = sender
        self.limiter = RateLimiter(global_limit=30, user_limit=1)

    async def send_user(self, telegram_id: int, text: str) -> None:
        if self.sender is not None:
            await self.limiter.acquire(user_id=telegram_id)
            await self.sender.send_message(telegram_id, text)

    async def send_admin(self, text: str) -> None:
        if self.sender is not None:
            await self.limiter.acquire(user_id=None)
            await self.sender.send_admin_alert(text)
