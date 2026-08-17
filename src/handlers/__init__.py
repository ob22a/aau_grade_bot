"""Telegram handlers package."""

from .commands.start import build_start_router
from .commands.registration import build_registration_router
from .commands.grades import build_grades_router
from .commands.admin import build_admin_router
from .commands.fallback import build_fallback_router

__all__ = [
    "build_start_router",
    "build_registration_router",
    "build_grades_router",
    "build_admin_router",
    "build_fallback_router",
]
