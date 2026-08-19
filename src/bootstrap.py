"""Application bootstrap for HTTP and Telegram runtime composition."""

from __future__ import annotations

import hmac
from contextlib import suppress
from typing import Any

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage

from clients.aau_portal_adapter import AAUPortalClient
from clients.telegram_adapter import AiogramTelegramNotificationSender
from clients.cache_adapter import InMemoryCache
from config import Settings
from crypto.cipher import AesGcmCipher
from handlers.commands.admin import build_admin_router
from handlers.commands.fallback import build_fallback_router
from handlers.commands.grades import build_grades_router
from handlers.commands.registration import build_registration_router
from handlers.commands.start import build_start_router
from handlers.commands.unregister import build_unregister_router
from handlers.commands.my_data import build_my_data_router
from services.container import ApplicationServices
from services.account_lifecycle.service import AccountLifecycleService
from services.admin.service import AdminService
from services.grades.service import GradeReadService
from services.notification.service import NotificationService
from services.registration.service import RegistrationService
from services.scheduler.service import SchedulerService
from services.scraper.service import ScraperService


def build_http_app(settings: Settings) -> web.Application:
    app = web.Application()

    async def health(_request: web.Request) -> web.Response:
        return web.Response(status=204)

    async def metrics(_request: web.Request) -> web.Response:
        if settings.metrics_secret is not None:
            provided = _request.headers.get("X-Admin-Secret", "")
            if not hmac.compare_digest(provided, settings.metrics_secret):
                return web.Response(status=401)
        return web.json_response({"status": "ok", "uptime": "available"})

    async def cron(_request: web.Request) -> web.Response:
        if settings.cron_secret is not None:
            provided = _request.headers.get("X-Cron-Secret", "")
            if not hmac.compare_digest(provided, settings.cron_secret):
                return web.Response(status=401)
        return web.json_response({"status": "accepted"})

    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    app.router.add_get("/metrics", metrics)
    app.router.add_post("/cron", cron)
    return app


def build_application_services(
    settings: Settings,
    bot: Bot | None = None,
    session_factory: Any | None = None,
) -> ApplicationServices:
    if not settings.encryption_key:
        raise ValueError("ENCRYPTION_KEY is required to build application services")

    portal_client = AAUPortalClient(settings)
    cipher = AesGcmCipher.from_base64_key(settings.encryption_key)
    sender = AiogramTelegramNotificationSender(bot, settings.admins_telegram_id) if bot is not None else None
    
    # Initialize cache
    if settings.redis_url:
        from clients.cache_adapter import RedisCache
        cache = RedisCache(settings.redis_url)
    else:
        cache = InMemoryCache()

    notification_service = NotificationService(sender)

    if session_factory is None and settings.database_url:
        with suppress(Exception):
            from database.connection import create_engine_from_url, create_session_factory
            engine = create_engine_from_url(settings.database_url)
            session_factory = create_session_factory(engine)

    return ApplicationServices(
        registration=RegistrationService(
            portal_client=portal_client,
            cipher=cipher,
            session_factory=session_factory,
            cache=cache,
        ),
        grades=GradeReadService(
            portal_client=portal_client,
            cipher=cipher,
            session_factory=session_factory,
            cache=cache,
            notification_service=notification_service,
        ),
        admin=AdminService(notifier=sender, session_factory=session_factory),
        scheduler=SchedulerService(notification_service=notification_service, portal_client=portal_client),
        lifecycle=AccountLifecycleService(notifier=sender, session_factory=session_factory),
        notification=notification_service,
        scraper=ScraperService(portal_client),
    )


def build_dispatcher(settings: Settings, services: ApplicationServices) -> Dispatcher:
    storage = MemoryStorage()
    if settings.redis_url:
        with suppress(Exception):
            storage = RedisStorage.from_url(settings.redis_url)
    dispatcher = Dispatcher(storage=storage)
    dispatcher.include_router(build_start_router(services))
    dispatcher.include_router(build_registration_router(services))
    dispatcher.include_router(build_grades_router(services))
    dispatcher.include_router(build_my_data_router(services))
    dispatcher.include_router(build_admin_router(settings, services))
    dispatcher.include_router(build_unregister_router(services))
    dispatcher.include_router(build_fallback_router(services))
    return dispatcher


def build_notification_sender(bot: Bot, settings: Settings) -> AiogramTelegramNotificationSender:
    return AiogramTelegramNotificationSender(bot, settings.admins_telegram_id)
