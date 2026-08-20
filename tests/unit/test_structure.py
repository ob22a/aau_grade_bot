"""Structure tests for Phase 6 handlers and bootstrap wiring."""

from __future__ import annotations

from dataclasses import dataclass

from aiohttp import web

from bootstrap import build_dispatcher, build_http_app
from config import Settings
from dto.bot import GradeReadResult, RegistrationResult, MetricsSnapshot
from services.container import ApplicationServices
from handlers import (
    build_admin_router,
    build_fallback_router,
    build_grades_router,
    build_registration_router,
    build_start_router,
)


@dataclass
class DummyRegistrationService:
    async def register(self, request):
        return type("Outcome", (), {"result": RegistrationResult(success=True, message="ok")})()


@dataclass
class DummyGradesService:
    async def read(self, request):
        return GradeReadResult(message="ok", cached=True)


@dataclass
class DummyAdminService:
    async def broadcast(self, request):
        return type("BroadcastResult", (), {"message": "broadcast ok", "recipients": 0})()

    async def update_setting(self, request):
        return type("SettingsUpdateResult", (), {"message": "setting ok"})()

    async def metrics_snapshot(self):
        return MetricsSnapshot(uptime_seconds=1)


@dataclass
class DummySchedulerService:
    async def run_once(self):
        return None


@dataclass
class DummyLifecycleService:
    async def request_deletion(self, request):
        return type("LifecycleResult", (), {"message": "queued", "deleted": True})()


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


def _services() -> ApplicationServices:
    return ApplicationServices(
        registration=DummyRegistrationService(),
        grades=DummyGradesService(),
        admin=DummyAdminService(),
        scheduler=DummySchedulerService(),
        lifecycle=DummyLifecycleService(),
        notification=DummyNotificationService(),
        scraper=DummyScraperService(),
    )


def test_http_app_builds() -> None:
    app = build_http_app(Settings())
    assert isinstance(app, web.Application)


def test_router_builders_return_objects() -> None:
    services = _services()
    assert build_start_router(services) is not None
    assert build_registration_router(services) is not None
    assert build_grades_router(services) is not None
    assert build_admin_router(Settings(), services) is not None
    assert build_fallback_router(services) is not None


def test_dispatcher_builds_with_services() -> None:
    services = _services()
    dispatcher = build_dispatcher(Settings(encryption_key=""), services)
    assert dispatcher is not None
