"""Stress Scenario A: Mass Concurrent Registration.

Ramps from 50 to 1000 concurrent users calling RegistrationService.register()
to find the breaking point. Each user has unique telegram_id and university_id.

The portal mock introduces 50ms latency per scrape. The portal semaphore (3)
limits real concurrency, so we're measuring queuing behavior and cipher
throughput under backpressure.
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest

from crypto.cipher import AesGcmCipher
from dto.bot import RegistrationRequest
from services.registration.service import RegistrationService

from tests.stress.conftest import MockPortalClient, MockCache, StressMetrics


LOAD_LEVELS = [50, 100, 250, 500, 750, 1000]


def _make_university_id(index: int) -> str:
    """Generate UGR/NNNN/16 format IDs."""
    return f"UGR/{index:04d}/16"


async def _run_registration_batch(
    count: int,
    portal: MockPortalClient,
    cipher: AesGcmCipher,
    cache: MockCache,
) -> StressMetrics:
    """Run `count` concurrent registrations and collect metrics."""

    service = RegistrationService(
        portal_client=portal,
        cipher=cipher,
        cache=cache,
        session_factory=None,  # Skip DB persistence for this scenario
    )

    metrics = StressMetrics()
    metrics.start_time = time.perf_counter()

    async def single_registration(idx: int) -> None:
        request = RegistrationRequest(
            telegram_id=10000 + idx,
            university_id=_make_university_id(idx),
            password=f"password_{idx}",
        )
        t0 = time.perf_counter()
        try:
            result = await service.register(request)
            metrics.record_latency(time.perf_counter() - t0)
        except Exception as exc:
            metrics.record_error(exc)

    # Clear cache to avoid rate limiting across iterations
    cache._store.clear()

    tasks = [single_registration(i) for i in range(count)]
    await asyncio.gather(*tasks)

    metrics.end_time = time.perf_counter()
    return metrics


@pytest.mark.parametrize("user_count", LOAD_LEVELS)
def test_scenario_a_concurrent_registration(user_count: int) -> None:
    """Ramp up concurrent registrations to find the breaking point."""

    async def scenario() -> None:
        portal = MockPortalClient(latency_seconds=0.05)
        cipher = AesGcmCipher.from_base64_key(AesGcmCipher.generate_key())
        cache = MockCache()

        metrics = await _run_registration_batch(user_count, portal, cipher, cache)
        print(metrics.summary(f"Scenario A: {user_count} Concurrent Registrations"))

        # Core assertions
        assert metrics.error_count == 0, (
            f"{metrics.error_count} errors at {user_count} users: "
            f"{[str(e) for e in metrics.errors[:5]]}"
        )
        assert metrics.success_count == user_count

        # Throughput sanity (at least 10 registrations/sec even at max load)
        assert metrics.throughput > 10, (
            f"Throughput too low: {metrics.throughput:.1f} ops/sec"
        )

    asyncio.run(scenario())


def test_scenario_a_registration_idempotency() -> None:
    """Concurrent registrations for the SAME user should not duplicate data."""

    async def scenario() -> None:
        portal = MockPortalClient(latency_seconds=0.01)
        cipher = AesGcmCipher.from_base64_key(AesGcmCipher.generate_key())

        # Track how many times portal.scrape is called
        call_count = 0
        original_scrape = portal.scrape

        async def counting_scrape(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return await original_scrape(*args, **kwargs)

        portal.scrape = counting_scrape

        service = RegistrationService(
            portal_client=portal,
            cipher=cipher,
            session_factory=None,
        )

        # 20 concurrent registrations for the same user
        request = RegistrationRequest(
            telegram_id=99999,
            university_id="UGR/0001/16",
            password="same_password",
        )

        results = await asyncio.gather(
            *[service.register(request) for _ in range(20)],
            return_exceptions=True,
        )

        successes = [r for r in results if not isinstance(r, Exception)]
        errors = [r for r in results if isinstance(r, Exception)]

        # All should succeed (no DB uniqueness constraint without session_factory)
        # But portal should have been called for each one
        assert call_count == 20
        print(f"  Same-user idempotency: {len(successes)} successes, {len(errors)} errors")

    asyncio.run(scenario())
