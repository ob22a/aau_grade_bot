"""Shared fixtures for the stress test suite.

Provides mock portal, mock cache, real cipher, and wired application services
for stress scenarios that test throughput and concurrency without hitting
real external services.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import pytest

from crypto.cipher import AesGcmCipher
from parser.models import (
    GradeReport,
    CourseGrade,
    AssessmentReference,
    GradeReportSummary,
    ProfilePageResult,
    StudentProfileData,
)


# ---------------------------------------------------------------------------
# Mock Portal Client (configurable latency)
# ---------------------------------------------------------------------------

@dataclass
class MockPortalClient:
    """Simulates AAU portal with configurable response latency."""

    latency_seconds: float = 0.2
    call_count: int = 0
    semaphore: asyncio.Semaphore | None = None

    async def scrape(
        self, username: str, password: str, student_id: str
    ) -> tuple[ProfilePageResult, list[GradeReport]]:
        if self.semaphore:
            async with self.semaphore:
                return await self._do_scrape()
        return await self._do_scrape()

    async def _do_scrape(self) -> tuple[ProfilePageResult, list[GradeReport]]:
        self.call_count += 1
        await asyncio.sleep(self.latency_seconds)

        profile = ProfilePageResult(
            profile=StudentProfileData(
                full_name="Stress Test User",
                student_id="UGR/0001/16",
                department="SITE",
                year_level="Year III",
            )
        )
        grades = GradeReport(
            academic_year="2023/2024",
            year_label="Year III",
            semester_label="Semester I",
            course_grades=(
                CourseGrade(
                    course_number=1,
                    course_name="Software Engineering",
                    course_code="SECT-3082",
                    credit_hours=3.0,
                    ects=5.0,
                    grade="A",
                    assessment=AssessmentReference(
                        academic_year_id="1", semester_id="1", course_id="101"
                    ),
                ),
            ),
            summary=GradeReportSummary(
                sgp=12.0, sgpa=4.0, cgp=12.0, cgpa=4.0, academic_status="Pass"
            ),
        )
        return profile, [grades]


# ---------------------------------------------------------------------------
# Mock Cache (in-memory dict with TTL)
# ---------------------------------------------------------------------------

@dataclass
class MockCache:
    """In-memory cache simulating Redis."""

    _store: dict[str, tuple[str, float]] = field(default_factory=dict)

    async def get(self, key: str) -> str | None:
        if key in self._store:
            value, expires_at = self._store[key]
            if time.time() < expires_at:
                return value
            del self._store[key]
        return None

    async def set(self, key: str, value: str, ttl_seconds: int = 1800) -> None:
        self._store[key] = (value, time.time() + ttl_seconds)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def acquire_lock(self, key: str, ttl_seconds: int = 30) -> bool:
        if key in self._store:
            _, expires_at = self._store[key]
            if time.time() < expires_at:
                return False
        self._store[key] = ("1", time.time() + ttl_seconds)
        return True

    async def release_lock(self, key: str) -> None:
        self._store.pop(key, None)


# ---------------------------------------------------------------------------
# Mock Notification Sender (tracks call timestamps)
# ---------------------------------------------------------------------------

@dataclass
class MockNotificationSender:
    """Tracks send timestamps for rate-limit verification."""

    calls: list[tuple[int, float]] = field(default_factory=list)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def send_message(self, telegram_id: int, text: str) -> None:
        async with self._lock:
            self.calls.append((telegram_id, time.time()))

    async def send_admin_alert(self, text: str) -> None:
        async with self._lock:
            self.calls.append((0, time.time()))


# ---------------------------------------------------------------------------
# Performance metrics helpers
# ---------------------------------------------------------------------------

@dataclass
class StressMetrics:
    """Collects and reports latency/throughput metrics."""

    latencies: list[float] = field(default_factory=list)
    errors: list[Exception] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0

    def record_latency(self, seconds: float) -> None:
        self.latencies.append(seconds)

    def record_error(self, exc: Exception) -> None:
        self.errors.append(exc)

    @property
    def total_time(self) -> float:
        return self.end_time - self.start_time

    @property
    def success_count(self) -> int:
        return len(self.latencies)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def throughput(self) -> float:
        if self.total_time <= 0:
            return 0
        return self.success_count / self.total_time

    def percentile(self, p: float) -> float:
        if not self.latencies:
            return 0.0
        sorted_l = sorted(self.latencies)
        idx = int(len(sorted_l) * p / 100)
        return sorted_l[min(idx, len(sorted_l) - 1)]

    def summary(self, title: str) -> str:
        if not self.latencies:
            return f"{title}: No successful operations"
        mean = sum(self.latencies) / len(self.latencies)
        return (
            f"\n{'=' * 60}\n"
            f" {title}\n"
            f"{'=' * 60}\n"
            f" Total time:    {self.total_time:.2f}s\n"
            f" Success rate:  {self.success_count}/{self.success_count + self.error_count}\n"
            f" Throughput:    {self.throughput:.1f} ops/sec\n"
            f" Mean latency:  {mean * 1000:.1f}ms\n"
            f" P50 latency:   {self.percentile(50) * 1000:.1f}ms\n"
            f" P95 latency:   {self.percentile(95) * 1000:.1f}ms\n"
            f" P99 latency:   {self.percentile(99) * 1000:.1f}ms\n"
            f" Errors:        {self.error_count}\n"
            f"{'=' * 60}"
        )


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_portal() -> MockPortalClient:
    return MockPortalClient(latency_seconds=0.05)


@pytest.fixture
def mock_cache() -> MockCache:
    return MockCache()


@pytest.fixture
def cipher() -> AesGcmCipher:
    return AesGcmCipher.from_base64_key(AesGcmCipher.generate_key())


@pytest.fixture
def mock_sender() -> MockNotificationSender:
    return MockNotificationSender()
