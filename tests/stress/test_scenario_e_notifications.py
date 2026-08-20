"""Stress Scenario E: Notification Throttle Compliance.

Verifies that the notification service respects Telegram's rate limits:
- Global: ~30 messages/second
- Per-chat: 1 message/second

If the notification service does NOT yet implement throttling, these tests
document the gap and XFail to indicate future work needed.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict

import pytest

from services.notification.service import NotificationService

from tests.stress.conftest import MockNotificationSender, StressMetrics


def _count_calls_per_second(calls: list[tuple[int, float]]) -> list[int]:
    """Group call timestamps into 1-second buckets and count per bucket."""
    if not calls:
        return []
    min_time = min(t for _, t in calls)
    buckets: dict[int, int] = defaultdict(int)
    for _, timestamp in calls:
        bucket = int(timestamp - min_time)
        buckets[bucket] += 1
    if not buckets:
        return []
    max_bucket = max(buckets.keys())
    return [buckets.get(i, 0) for i in range(max_bucket + 1)]


def _count_per_chat_per_second(calls: list[tuple[int, float]]) -> dict[int, list[int]]:
    """Group calls by chat_id, then into 1-second buckets."""
    by_chat: dict[int, list[float]] = defaultdict(list)
    for chat_id, timestamp in calls:
        by_chat[chat_id].append(timestamp)

    result: dict[int, list[int]] = {}
    for chat_id, timestamps in by_chat.items():
        min_time = min(timestamps)
        buckets: dict[int, int] = defaultdict(int)
        for t in timestamps:
            bucket = int(t - min_time)
            buckets[bucket] += 1
        if buckets:
            max_bucket = max(buckets.keys())
            result[chat_id] = [buckets.get(i, 0) for i in range(max_bucket + 1)]
    return result


@pytest.mark.xfail(
    reason="Notification throttling not yet implemented — documenting the gap",
    strict=False,
)
def test_scenario_e_global_rate_limit() -> None:
    """Send 100 notifications rapidly and verify ≤30 per second."""

    async def scenario() -> None:
        sender = MockNotificationSender()
        service = NotificationService(sender=sender)

        metrics = StressMetrics()
        metrics.start_time = time.perf_counter()

        # Fire 100 notifications to 100 different users
        tasks = []
        for i in range(100):
            tasks.append(service.send_user(60000 + i, f"Notification {i}"))

        await asyncio.gather(*tasks)
        metrics.end_time = time.perf_counter()

        # Analyze call distribution
        calls_per_second = _count_calls_per_second(sender.calls)
        max_in_any_second = max(calls_per_second) if calls_per_second else 0

        print(f"\n  Global rate limit test:")
        print(f"  Total calls: {len(sender.calls)}")
        print(f"  Calls per second: {calls_per_second}")
        print(f"  Max in any 1s window: {max_in_any_second}")

        # Telegram limit: ~30 msg/sec globally
        assert max_in_any_second <= 30, (
            f"Exceeded global rate limit: {max_in_any_second} msgs in 1 second "
            f"(limit: 30). Distribution: {calls_per_second}"
        )

    asyncio.run(scenario())


@pytest.mark.xfail(
    reason="Per-chat throttling not yet implemented — documenting the gap",
    strict=False,
)
def test_scenario_e_per_chat_rate_limit() -> None:
    """Send multiple notifications to the same user and verify ≤1 per second."""

    async def scenario() -> None:
        sender = MockNotificationSender()
        service = NotificationService(sender=sender)

        # Send 10 messages to the same user rapidly
        target_user = 70000
        tasks = [
            service.send_user(target_user, f"Message {i}")
            for i in range(10)
        ]
        await asyncio.gather(*tasks)

        # Analyze per-chat distribution
        per_chat = _count_per_chat_per_second(sender.calls)
        if target_user in per_chat:
            max_per_second = max(per_chat[target_user])
            print(f"\n  Per-chat rate limit test:")
            print(f"  User {target_user} calls per second: {per_chat[target_user]}")
            print(f"  Max in any 1s window: {max_per_second}")

            assert max_per_second <= 1, (
                f"Exceeded per-chat rate limit: {max_per_second} msgs in 1 second "
                f"to user {target_user} (limit: 1)"
            )

    asyncio.run(scenario())


def test_scenario_e_notification_throughput_without_throttle() -> None:
    """Baseline: measure raw notification throughput (no throttling).

    This test always passes — it documents the current throughput
    to compare against when throttling is implemented.
    """

    async def scenario() -> None:
        sender = MockNotificationSender()
        service = NotificationService(sender=sender)

        metrics = StressMetrics()
        metrics.start_time = time.perf_counter()

        for i in range(500):
            t0 = time.perf_counter()
            await service.send_user(80000 + i, f"Message {i}")
            metrics.record_latency(time.perf_counter() - t0)

        metrics.end_time = time.perf_counter()

        print(metrics.summary("Scenario E: Raw Notification Throughput (500 msgs, no throttle)"))

        calls_per_second = _count_calls_per_second(sender.calls)
        max_burst = max(calls_per_second) if calls_per_second else 0
        print(f"  Peak burst: {max_burst} msgs/sec")
        print(f"  [WARNING] Telegram limit is 30/sec -- throttling needed if burst > 30")

    asyncio.run(scenario())
