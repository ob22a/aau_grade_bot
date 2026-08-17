"""Unit tests for Phase 6 services."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace

from crypto.cipher import AesGcmCipher
from dto.bot import (
    AccountDeletionRequest,
    BroadcastRequest,
    GradeReadRequest,
    RegistrationRequest,
)
from parser.models import GradeReport, ProfilePageResult, StudentProfileData, GradeReportSummary, AssessmentReference, CourseGrade
from services.account_lifecycle.service import AccountLifecycleService
from services.admin.service import AdminService
from services.grades.service import GradeReadService
from services.registration.service import RegistrationService
from services.scheduler.service import SchedulerService


@dataclass
class DummyCache:
    value: str | None = None
    set_calls: list[tuple[str, str, int | None]] = None

    def __post_init__(self) -> None:
        if self.set_calls is None:
            self.set_calls = []

    async def get(self, key: str) -> str | None:
        return self.value

    async def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        self.set_calls.append((key, value, ttl_seconds))


@dataclass
class DummyListRepo:
    added: list[object] = None
    removed: list[object] = None

    def __post_init__(self) -> None:
        if self.added is None:
            self.added = []
        if self.removed is None:
            self.removed = []

    async def add(self, item) -> None:
        self.added.append(item)

    async def remove(self, item) -> None:
        self.removed.append(item)


@dataclass
class DummyUserRepo:
    user: object | None = None
    removed: list[object] = None

    def __post_init__(self) -> None:
        if self.removed is None:
            self.removed = []

    async def get_by_telegram_id(self, telegram_id: int):
        return self.user

    async def remove(self, user) -> None:
        self.removed.append(user)


@dataclass
class DummyPortal:
    calls: list[tuple[str, str, str]] = None

    def __post_init__(self) -> None:
        if self.calls is None:
            self.calls = []

    async def scrape(self, university_id: str, password: str, student_id: str):
        self.calls.append((university_id, password, student_id))
        profile = ProfilePageResult(
            profile=StudentProfileData(
                full_name="Test User",
                student_id=student_id,
                department="SITE",
                year_level="Year III",
            )
        )
        grade_report = GradeReport(
            academic_year="2025/26",
            year_label="III",
            semester_label="One",
            course_grades=(
                CourseGrade(
                    course_number=1,
                    course_name="Algorithms",
                    course_code="SECT-1001",
                    credit_hours=3,
                    ects=5,
                    grade="A",
                    assessment=AssessmentReference(
                        academic_year_id="1",
                        semester_id="2",
                        course_id="3",
                    ),
                ),
            ),
            summary=GradeReportSummary(sgp=4.0, sgpa=4.0, cgp=4.0, cgpa=4.0, academic_status="Good"),
        )
        return profile, grade_report


@dataclass
class DummyNotifier:
    sent_users: list[tuple[int, str]] = None
    admin_alerts: list[str] = None

    def __post_init__(self) -> None:
        if self.sent_users is None:
            self.sent_users = []
        if self.admin_alerts is None:
            self.admin_alerts = []

    async def send_message(self, telegram_id: int, text: str) -> None:
        self.sent_users.append((telegram_id, text))

    async def send_admin_alert(self, text: str) -> None:
        self.admin_alerts.append(text)

    async def send_admin(self, text: str) -> None:
        self.admin_alerts.append(text)


@dataclass
class DummyLock:
    acquire_result: bool = True
    acquired_keys: list[str] = None
    released_keys: list[str] = None

    def __post_init__(self) -> None:
        if self.acquired_keys is None:
            self.acquired_keys = []
        if self.released_keys is None:
            self.released_keys = []

    async def acquire(self, key: str, ttl_seconds: int) -> bool:
        self.acquired_keys.append(key)
        return self.acquire_result

    async def release(self, key: str) -> None:
        self.released_keys.append(key)


async def _registration_round_trip() -> None:
    portal = DummyPortal()
    user_repo = DummyListRepo()
    credential_repo = DummyListRepo()
    audit_repo = DummyListRepo()
    cache = DummyCache()
    cipher = AesGcmCipher.from_base64_key(AesGcmCipher.generate_key())

    service = RegistrationService(
        portal_client=portal,
        cipher=cipher,
        user_repository=user_repo,
        credential_repository=credential_repo,
        audit_repository=audit_repo,
        cache=cache,
    )

    outcome = await service.register(
        RegistrationRequest(
            telegram_id=1,
            university_id=" ugr/0000/16 ",
            password="password123",
        )
    )

    assert outcome.result.success is True
    assert portal.calls[0][0] == "UGR/0000/16"
    assert user_repo.added[0]["full_name"] == "Test User"
    assert credential_repo.added[0]["algorithm"] == "AES-256-GCM"
    assert len(credential_repo.added[0]["iv"]) > 0
    assert audit_repo.added[0]["action"] == "register"
    assert cache.set_calls[0][0] == "registration:1"


def test_registration_service_persists_and_encrypts() -> None:
    asyncio.run(_registration_round_trip())


async def _grade_read_round_trip() -> None:
    cache = DummyCache(value="cached grades text")
    service = GradeReadService(cache=cache, repository=None)

    result = await service.read(GradeReadRequest(telegram_id=5))
    assert result.cached is True
    assert result.message == "cached grades text"


def test_grade_read_service_uses_cache_first() -> None:
    asyncio.run(_grade_read_round_trip())


async def _admin_broadcast_round_trip() -> None:
    notifier = DummyNotifier()
    service = AdminService(notifier=notifier)

    result = await service.broadcast(
        BroadcastRequest(admin_telegram_id=99, message="Hello", recipient_ids=(10, 11))
    )

    assert result.recipients == 2
    assert notifier.sent_users == [(10, "Hello"), (11, "Hello")]


def test_admin_service_broadcasts_to_recipients() -> None:
    asyncio.run(_admin_broadcast_round_trip())


async def _scheduler_round_trip() -> None:
    lock = DummyLock(acquire_result=True)
    service = SchedulerService(lock=lock)
    result = await service.run_once()

    assert result.skipped is False
    assert lock.acquired_keys == ["cron:run"]
    assert lock.released_keys == ["cron:run"]


def test_scheduler_service_uses_distributed_lock() -> None:
    asyncio.run(_scheduler_round_trip())


async def _account_lifecycle_round_trip() -> None:
    user = object()
    user_repo = DummyUserRepo(user=user)
    audit_repo = DummyListRepo()
    service = AccountLifecycleService(user_repository=user_repo, audit_repository=audit_repo)

    result = await service.request_deletion(AccountDeletionRequest(telegram_id=7, confirm=True))

    assert result.deleted is True
    assert user_repo.removed == [user]
    assert audit_repo.added[0]["action"] == "account_deletion_requested"


def test_account_lifecycle_service_deletes_when_confirmed() -> None:
    asyncio.run(_account_lifecycle_round_trip())
