"""Stress Scenario C: Cron Cohort Scan Under User Load.

Simulates a background cohort scan processing 10 cohorts (10 users each)
while 50 concurrent user-facing grade requests arrive. Verifies that:
1. User-facing requests are not starved
2. The cohort scan completes within timeout
3. The portal semaphore is shared correctly without deadlock
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


NUM_COHORTS = 10
USERS_PER_COHORT = 10
CONCURRENT_USER_REQUESTS = 50
SCAN_TIMEOUT_SECONDS = 30


async def _simulate_cohort_scan(
    portal: MockPortalClient,
    cipher: AesGcmCipher,
    scan_metrics: StressMetrics,
) -> None:
    """Simulate scanning all cohorts sequentially (each cohort's users in parallel)."""
    for cohort_idx in range(NUM_COHORTS):
        async def scan_user(user_idx: int) -> None:
            university_id = f"UGR/{cohort_idx:02d}{user_idx:02d}/16"
            t0 = time.perf_counter()
            try:
                await portal.scrape(university_id, "password", university_id)
                scan_metrics.record_latency(time.perf_counter() - t0)
            except Exception as exc:
                scan_metrics.record_error(exc)

        tasks = [scan_user(i) for i in range(USERS_PER_COHORT)]
        await asyncio.gather(*tasks)


async def _simulate_user_traffic(
    service: GradeReadService,
    user_metrics: StressMetrics,
    duration_seconds: float = 5.0,
) -> None:
    """Simulate continuous user grade requests for a duration."""
    end_time = time.time() + duration_seconds
    user_idx = 0

    async def single_request(idx: int) -> None:
        request = GradeReadRequest(telegram_id=40000 + idx, page_index=0)
        t0 = time.perf_counter()
        try:
            await service.read(request)
            user_metrics.record_latency(time.perf_counter() - t0)
        except Exception as exc:
            user_metrics.record_error(exc)

    while time.time() < end_time:
        batch = [single_request(user_idx + i) for i in range(10)]
        user_idx += 10
        await asyncio.gather(*batch)
        await asyncio.sleep(0.1)  # Brief pause between batches


def test_scenario_c_cohort_scan_under_user_load() -> None:
    """Cohort scan and user traffic run simultaneously."""

    async def scenario() -> None:
        # Shared portal with semaphore (like production)
        portal = MockPortalClient(latency_seconds=0.05)
        portal.semaphore = asyncio.Semaphore(3)  # matches config.portal_semaphore_limit

        cipher = AesGcmCipher.from_base64_key(AesGcmCipher.generate_key())
        cache = MockCache()

        # Pre-populate some cache entries so user requests have cache hits
        for i in range(25):
            await cache.set(
                f"grades:{40000 + i}",
                json.dumps(["Cached grade page"]),
            )

        service = GradeReadService(
            cache=cache,
            portal_client=portal,
            cipher=cipher,
        )

        scan_metrics = StressMetrics()
        user_metrics = StressMetrics()

        scan_metrics.start_time = time.perf_counter()
        user_metrics.start_time = time.perf_counter()

        # Run both concurrently
        scan_task = asyncio.create_task(
            _simulate_cohort_scan(portal, cipher, scan_metrics)
        )
        user_task = asyncio.create_task(
            _simulate_user_traffic(service, user_metrics, duration_seconds=5.0)
        )

        # Wait for scan with timeout
        try:
            await asyncio.wait_for(scan_task, timeout=SCAN_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            pytest.fail(f"Cohort scan did not complete within {SCAN_TIMEOUT_SECONDS}s")

        # Cancel user traffic (it runs on a timer)
        user_task.cancel()
        try:
            await user_task
        except asyncio.CancelledError:
            pass

        scan_metrics.end_time = time.perf_counter()
        user_metrics.end_time = time.perf_counter()

        print(scan_metrics.summary(
            f"Scenario C: Cohort Scan ({NUM_COHORTS} cohorts × {USERS_PER_COHORT} users)"
        ))
        print(user_metrics.summary(
            f"Scenario C: User Traffic (concurrent with scan)"
        ))

        # Assertions
        assert scan_metrics.error_count == 0, "Cohort scan had errors"
        assert scan_metrics.success_count == NUM_COHORTS * USERS_PER_COHORT

        # User traffic should not be completely starved
        assert user_metrics.success_count > 0, "User traffic was completely starved"
        assert user_metrics.error_count == 0, "User traffic had errors"

        # User P95 latency should be reasonable (< 2s)
        if user_metrics.latencies:
            assert user_metrics.percentile(95) < 2.0, (
                f"User P95 latency too high: {user_metrics.percentile(95) * 1000:.0f}ms"
            )

    asyncio.run(scenario())


def test_scenario_c_semaphore_fairness() -> None:
    """Verify that the semaphore doesn't deadlock under heavy contention."""

    async def scenario() -> None:
        portal = MockPortalClient(latency_seconds=0.02)
        portal.semaphore = asyncio.Semaphore(3)

        metrics = StressMetrics()
        metrics.start_time = time.perf_counter()

        async def contend(idx: int) -> None:
            t0 = time.perf_counter()
            try:
                await portal.scrape(f"UGR/{idx:04d}/16", "pass", f"UGR/{idx:04d}/16")
                metrics.record_latency(time.perf_counter() - t0)
            except Exception as exc:
                metrics.record_error(exc)

        # 100 tasks competing for 3 semaphore slots
        await asyncio.gather(*[contend(i) for i in range(100)])
        metrics.end_time = time.perf_counter()

        print(metrics.summary("Scenario C: Semaphore Fairness (100 tasks, 3 slots)"))

        assert metrics.error_count == 0
        assert metrics.success_count == 100

    asyncio.run(scenario())
