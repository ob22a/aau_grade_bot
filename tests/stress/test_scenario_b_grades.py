"""Stress Scenario B: Concurrent Grade Reads with Cache Hit/Miss Mix.

Ramps from 50 to 1000 concurrent grade read requests. Half are cache hits
(pre-populated), half are cache misses that trigger portal scrapes through
the semaphore.

Measures cache-hit latency, cache-miss latency under semaphore queuing,
and total throughput.
"""

from __future__ import annotations

import asyncio
import json
import time

import pytest

from crypto.cipher import AesGcmCipher
from dto.bot import GradeReadRequest
from services.grades.service import GradeReadService

from tests.stress.conftest import MockPortalClient, MockCache, StressMetrics


LOAD_LEVELS = [50, 100, 250, 500, 750, 1000]


async def _run_grade_read_batch(
    count: int,
    portal: MockPortalClient,
    cipher: AesGcmCipher,
    cache: MockCache,
) -> tuple[StressMetrics, StressMetrics]:
    """Run `count` concurrent grade reads (half cached, half not).

    Returns (cache_hit_metrics, cache_miss_metrics).
    """
    service = GradeReadService(
        cache=cache,
        portal_client=portal,
        cipher=cipher,
    )

    # Pre-populate cache for first half of users
    half = count // 2
    sample_page = "🎓 *AAU Grade Report*\n📅 *Academic Year:* 2023/2024\n📘 *Semester:* I"
    for i in range(half):
        telegram_id = 20000 + i
        await cache.set(f"grades:{telegram_id}", json.dumps([sample_page, sample_page]))

    hit_metrics = StressMetrics()
    miss_metrics = StressMetrics()

    async def single_read(idx: int) -> None:
        telegram_id = 20000 + idx
        is_cache_hit = idx < half
        metrics = hit_metrics if is_cache_hit else miss_metrics

        request = GradeReadRequest(telegram_id=telegram_id, page_index=0)
        t0 = time.perf_counter()
        try:
            result = await service.read(request)
            latency = time.perf_counter() - t0
            metrics.record_latency(latency)
        except Exception as exc:
            metrics.record_error(exc)

    overall_start = time.perf_counter()
    tasks = [single_read(i) for i in range(count)]
    await asyncio.gather(*tasks)
    overall_end = time.perf_counter()

    hit_metrics.start_time = overall_start
    hit_metrics.end_time = overall_end
    miss_metrics.start_time = overall_start
    miss_metrics.end_time = overall_end

    return hit_metrics, miss_metrics


@pytest.mark.parametrize("user_count", LOAD_LEVELS)
def test_scenario_b_concurrent_grade_reads(user_count: int) -> None:
    """Ramp up concurrent grade reads to find the breaking point."""

    async def scenario() -> None:
        portal = MockPortalClient(latency_seconds=0.05)
        cipher = AesGcmCipher.from_base64_key(AesGcmCipher.generate_key())
        cache = MockCache()

        hit_metrics, miss_metrics = await _run_grade_read_batch(
            user_count, portal, cipher, cache
        )

        print(hit_metrics.summary(f"Scenario B Cache HITS ({user_count // 2} users)"))
        print(miss_metrics.summary(f"Scenario B Cache MISSES ({user_count - user_count // 2} users)"))

        # Cache hits must be fast
        assert hit_metrics.error_count == 0
        if hit_metrics.latencies:
            assert hit_metrics.percentile(95) < 0.1, (
                f"Cache hit P95 too slow: {hit_metrics.percentile(95) * 1000:.1f}ms"
            )

        # Cache misses: errors are acceptable at very high load, but track them
        total_errors = hit_metrics.error_count + miss_metrics.error_count
        total_ops = hit_metrics.success_count + miss_metrics.success_count
        error_rate = total_errors / user_count if user_count > 0 else 0

        assert error_rate < 0.05, (
            f"Error rate {error_rate:.1%} exceeds 5% at {user_count} users"
        )

    asyncio.run(scenario())


def test_scenario_b_pagination_under_load() -> None:
    """50 users rapidly paginating through grade pages concurrently."""

    async def scenario() -> None:
        cache = MockCache()
        # Each user has 5 pages
        for i in range(50):
            pages = [f"Page {p} for user {i}" for p in range(5)]
            await cache.set(f"grades:{30000 + i}", json.dumps(pages))

        service = GradeReadService(cache=cache)
        metrics = StressMetrics()
        metrics.start_time = time.perf_counter()

        async def paginate(user_idx: int) -> None:
            telegram_id = 30000 + user_idx
            for page in range(5):
                request = GradeReadRequest(telegram_id=telegram_id, page_index=page)
                t0 = time.perf_counter()
                try:
                    result = await service.read(request)
                    metrics.record_latency(time.perf_counter() - t0)
                    assert result.current_page == page
                    assert result.total_pages == 5
                except Exception as exc:
                    metrics.record_error(exc)

        tasks = [paginate(i) for i in range(50)]
        await asyncio.gather(*tasks)
        metrics.end_time = time.perf_counter()

        print(metrics.summary("Scenario B: 50 Users × 5 Pages Pagination"))
        assert metrics.error_count == 0
        assert metrics.success_count == 250  # 50 users × 5 pages

    asyncio.run(scenario())
