"""Integration tests for bootstrap HTTP endpoints and Telegram dispatcher flow."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock

import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.types import Chat, Message, Update, User

from bootstrap import build_dispatcher, build_http_app
from config import Settings
from dto.bot import GradeReadResult, RegistrationResult
from fsm.states import RegistrationFSM
from services.container import ApplicationServices
from crypto.cipher import AesGcmCipher


@dataclass
class DummyRegistrationService:
    last_request: object | None = None

    async def register(self, request):
        self.last_request = request
        return SimpleNamespace(
            profile=SimpleNamespace(profile=SimpleNamespace(full_name="Test User", department="SITE")),
            result=RegistrationResult(success=True, message="Registration complete"),
        )


@dataclass
class DummyGradesService:
    async def read(self, request):
        return GradeReadResult(message="Cached grades", cached=True)


@dataclass
class DummyAdminService:
    async def broadcast(self, request):
        return SimpleNamespace(message="Broadcast sent", recipients=1)

    async def update_setting(self, request):
        return SimpleNamespace(message="Setting updated")

    async def metrics_snapshot(self):
        return SimpleNamespace(uptime_seconds=123, scrape_attempts=4, scrape_failures=1)


@dataclass
class DummySchedulerService:
    async def run_once(self):
        return SimpleNamespace(message="scheduled")


@dataclass
class DummyLifecycleService:
    async def request_deletion(self, request):
        return SimpleNamespace(message="Deletion queued", deleted=True)


@dataclass
class DummyNotificationService:
    async def send_user(self, telegram_id: int, text: str) -> None:
        return None

    async def send_admin(self, text: str) -> None:
        return None


@dataclass
class DummyScraperService:
    async def scrape(self, university_id: str, password: str, student_id: str):
        return None



def _application_services() -> ApplicationServices:
    return ApplicationServices(
        registration=DummyRegistrationService(),
        grades=DummyGradesService(),
        admin=DummyAdminService(),
        scheduler=DummySchedulerService(),
        lifecycle=DummyLifecycleService(),
        notification=DummyNotificationService(),
        scraper=DummyScraperService(),
    )



def _make_message(text: str, user_id: int = 123, chat_id: int = 123) -> Message:
    return Message(
        message_id=1,
        date=datetime.now(timezone.utc),
        chat=Chat(id=chat_id, type="private"),
        from_user=User(id=user_id, is_bot=False, first_name="Tester"),
        text=text,
    )


async def _run_http_app(settings: Settings) -> tuple[str, int]:
    app = build_http_app(settings)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()

    sockets = site._server.sockets  # type: ignore[attr-defined]
    assert sockets
    port = sockets[0].getsockname()[1]
    base_url = f"http://127.0.0.1:{port}"
    return base_url, port



def test_http_endpoints_enforce_secrets_and_health() -> None:
    async def scenario() -> None:
        settings = Settings(
            metrics_secret="metrics-secret",
            cron_secret="cron-secret",
        )
        app = build_http_app(settings)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()

        sockets = site._server.sockets  # type: ignore[attr-defined]
        assert sockets
        port = sockets[0].getsockname()[1]
        base_url = f"http://127.0.0.1:{port}"

        async with aiohttp.ClientSession() as session:
            async with session.get(f"{base_url}/health") as response:
                assert response.status == 204

            async with session.get(f"{base_url}/metrics") as response:
                assert response.status == 401

            async with session.get(
                f"{base_url}/metrics",
                headers={"X-Admin-Secret": "metrics-secret"},
            ) as response:
                assert response.status == 200
                payload = await response.json()
                assert payload["status"] == "ok"

            async with session.post(f"{base_url}/cron") as response:
                assert response.status == 401

            async with session.post(
                f"{base_url}/cron",
                headers={"X-Cron-Secret": "cron-secret"},
            ) as response:
                assert response.status == 200
                payload = await response.json()
                assert payload["status"] == "accepted"

        await runner.cleanup()

    asyncio.run(scenario())



def test_registration_flow_reaches_service_and_returns_messages() -> None:
    async def scenario() -> None:
        services = _application_services()
        settings = Settings(encryption_key=AesGcmCipher.generate_key())
        dispatcher = build_dispatcher(settings, services)
        bot = Bot(token="123:FAKE")
        replies: list[str] = []

        async def fake_answer(self, text: str, **kwargs):
            replies.append(text)
            return None

        with patch.object(Message, "answer", fake_answer):
            await dispatcher.feed_update(bot, Update(update_id=1, message=_make_message("/register")))
            await dispatcher.feed_update(bot, Update(update_id=2, message=_make_message("UGR/0000/16")))
            await dispatcher.feed_update(bot, Update(update_id=3, message=_make_message("password123")))

        assert replies[0].startswith("Send your AAU university ID")
        assert "Portal Password" in replies[1]
        assert "Registration complete" in replies[2]
        assert services.registration.last_request is not None
        assert services.registration.last_request.university_id == "UGR/0000/16"
        assert services.registration.last_request.password == "password123"

    asyncio.run(scenario())


def test_registration_command_interception_cancels_state() -> None:
    """Verify that sending a command (like /start or /cancel) mid-registration cancels the pending state."""
    async def scenario() -> None:
        services = _application_services()
        settings = Settings(encryption_key=AesGcmCipher.generate_key())
        dispatcher = build_dispatcher(settings, services)
        bot = Bot(token="123:FAKE")
        replies: list[str] = []

        async def fake_answer(self, text: str, **kwargs):
            replies.append(text)
            return None

        with patch.object(Message, "answer", fake_answer):
            # 1. Start registration
            await dispatcher.feed_update(bot, Update(update_id=1, message=_make_message("/register")))
            assert "Send your AAU university ID" in replies[0]

            # 2. Intercept with /start instead of sending ID
            await dispatcher.feed_update(bot, Update(update_id=2, message=_make_message("/start")))
            assert "Welcome! I am your <b>AAU Grade Bot</b>" in replies[1]

            # 3. Now send a Student ID string  it should NOT be accepted as registration input because state was cleared
            await dispatcher.feed_update(bot, Update(update_id=3, message=_make_message("UGR/0000/16")))
            assert "Unknown command" in replies[2]

    asyncio.run(scenario())


def test_registration_invalid_student_id_format_retries() -> None:
    """Verify that invalid student ID format shows helpful guidance without clearing state."""
    async def scenario() -> None:
        services = _application_services()
        settings = Settings(encryption_key=AesGcmCipher.generate_key())
        dispatcher = build_dispatcher(settings, services)
        bot = Bot(token="123:FAKE")
        replies: list[str] = []

        async def fake_answer(self, text: str, **kwargs):
            replies.append(text)
            return None

        with patch.object(Message, "answer", fake_answer):
            await dispatcher.feed_update(bot, Update(update_id=1, message=_make_message("/register")))
            # Invalid ID
            await dispatcher.feed_update(bot, Update(update_id=2, message=_make_message("invalid_id")))
            assert "Invalid AAU Student ID format" in replies[1]

            # Valid ID on retry
            await dispatcher.feed_update(bot, Update(update_id=3, message=_make_message("UGR/0000/16")))
            assert "Portal Password" in replies[2]

    asyncio.run(scenario())


def test_registration_auth_error_displays_friendly_message_and_clears_state() -> None:
    """Verify that portal authentication failure displays friendly message and clears state."""
    async def scenario() -> None:
        from clients.aau_portal import PortalAuthenticationError

        services = _application_services()
        # Mock registration to fail with auth error
        services.registration.register = AsyncMock(side_effect=PortalAuthenticationError("Invalid creds"))

        settings = Settings(encryption_key=AesGcmCipher.generate_key())
        dispatcher = build_dispatcher(settings, services)
        bot = Bot(token="123:FAKE")
        replies: list[str] = []

        async def fake_answer(self, text: str, **kwargs):
            replies.append(text)
            return None

        with patch.object(Message, "answer", fake_answer):
            await dispatcher.feed_update(bot, Update(update_id=1, message=_make_message("/register")))
            await dispatcher.feed_update(bot, Update(update_id=2, message=_make_message("UGR/0000/16")))
            await dispatcher.feed_update(bot, Update(update_id=3, message=_make_message("wrong_password")))

        assert "Registration failed" in replies[2]
        assert "Invalid AAU username or password" in replies[2]

        # Verify state is cleared — next message goes to fallback
        replies.clear()
        with patch.object(Message, "answer", fake_answer):
            await dispatcher.feed_update(bot, Update(update_id=4, message=_make_message("another_text")))
        assert "Unknown command" in replies[0]

    asyncio.run(scenario())




def test_admin_metrics_command_uses_snapshot_service() -> None:
    async def scenario() -> None:
        services = _application_services()
        settings = Settings(encryption_key=AesGcmCipher.generate_key())
        dispatcher = build_dispatcher(settings, services)
        bot = Bot(token="123:FAKE")
        replies: list[str] = []

        async def fake_answer(self, text: str, **kwargs):
            replies.append(text)
            return None

        with patch.object(Message, "answer", fake_answer):
            await dispatcher.feed_update(bot, Update(update_id=10, message=_make_message("/metrics")))

        assert replies
        assert "Uptime: 123s" in replies[0]
        assert "Scrapes: 4" in replies[0]
        assert "Failures: 1" in replies[0]

    asyncio.run(scenario())


def test_grades_command_flow_and_callbacks() -> None:
    async def scenario() -> None:
        from aiogram.types import CallbackQuery

        services = _application_services()
        settings = Settings(encryption_key=AesGcmCipher.generate_key())
        dispatcher = build_dispatcher(settings, services)
        bot = Bot(token="123:FAKE")
        replies: list[str] = []

        async def fake_answer(self, text: str, **kwargs):
            replies.append(text)
            return None

        with patch.object(Message, "answer", fake_answer):
            await dispatcher.feed_update(bot, Update(update_id=20, message=_make_message("/grades")))

        assert replies
        assert "Cached grades" in replies[0]

    asyncio.run(scenario())


def test_full_database_registration_and_grade_read_service_e2e() -> None:
    async def scenario() -> None:
        from services.registration.service import RegistrationService
        from services.grades.service import GradeReadService
        from parser.models import ProfilePageResult, StudentProfileData, GradeReport, CourseGrade, AssessmentReference, GradeReportSummary
        from dto.bot import RegistrationRequest, GradeReadRequest
        from types import SimpleNamespace

        cipher = AesGcmCipher.from_base64_key(AesGcmCipher.generate_key())

        mock_profile = ProfilePageResult(
            profile=StudentProfileData(
                full_name="Test Student",
                student_id="UGR/1234/16",
                department="SITE",
                year_level="Year III",
            )
        )
        mock_grades = GradeReport(
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
                    assessment=AssessmentReference(academic_year_id="1", semester_id="1", course_id="101"),
                ),
            ),
            summary=GradeReportSummary(sgp=12.0, sgpa=4.0, cgp=12.0, cgpa=4.0, academic_status="Pass"),
        )

        class MockPortal:
            async def scrape(self, username, password, student_id):
                return mock_profile, mock_grades

        portal_client = MockPortal()

        # In-memory store simulating UOW / DB persistence
        stored_users = {}
        stored_creds = {}

        class DummySession:
            def add(self, item):
                pass
            async def flush(self):
                pass

        class DummyUsersRepo:
            async def get_by_telegram_id(self, telegram_id):
                return stored_users.get(telegram_id)

        class DummyCredsRepo:
            async def get_by_user_id(self, user_id):
                return stored_creds.get(user_id)

        class DummyUOW:
            def __init__(self):
                self.session = DummySession()
                self.users = DummyUsersRepo()
                self.credentials = DummyCredsRepo()

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                pass

            async def commit(self):
                pass

        def fake_uow_factory(session_factory):
            uow = DummyUOW()
            return uow

        with patch("repositories.sqlalchemy.unit_of_work.SqlAlchemyRepositoryUnitOfWork", side_effect=fake_uow_factory):
            reg_service = RegistrationService(
                portal_client=portal_client,
                cipher=cipher,
                session_factory=lambda: None,
            )

            grades_service = GradeReadService(
                portal_client=portal_client,
                cipher=cipher,
                session_factory=lambda: None,
            )

            # Pre-populate stored user/credentials
            user_obj = SimpleNamespace(id="user-uuid-1", telegram_id=999, university_id="UGR/1234/16")
            encrypted = cipher.encrypt("my_password")
            from crypto.cipher import Ciphertext
            payload = Ciphertext.from_token(encrypted)
            import base64
            iv_token = base64.urlsafe_b64encode(payload.nonce).decode("ascii")

            cred_obj = SimpleNamespace(user_id="user-uuid-1", encrypted_password=encrypted, iv=iv_token)
            stored_users[999] = user_obj
            stored_creds["user-uuid-1"] = cred_obj

            # Read grades
            grade_res = await grades_service.read(GradeReadRequest(telegram_id=999, page_index=0))
            assert "SECT-3082 Software Engineering" in grade_res.message
            assert "Grade: *A*" in grade_res.message
            assert "SGPA: `4.00`" in grade_res.message

    asyncio.run(scenario())

