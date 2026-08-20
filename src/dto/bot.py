"""Immutable application command and result DTOs."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RegistrationRequest:
    telegram_id: int
    university_id: str
    password: str
    campus: str | None = None
    department_id: str | None = None
    section: str | None = None


@dataclass(frozen=True)
class RegistrationResult:
    success: bool
    message: str


@dataclass(frozen=True)
class GradeReadRequest:
    telegram_id: int
    force_refresh: bool = False
    year_filter: str | None = None
    semester_filter: str | None = None
    page_index: int = 0


from typing import Any
@dataclass(frozen=True)
class GradeReadResult:
    message: str
    cached: bool = False
    current_page: int = 0
    total_pages: int = 1
    report: Any | None = None



@dataclass(frozen=True)
class BroadcastRequest:
    admin_telegram_id: int
    message: str
    recipient_ids: tuple[int, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SettingsUpdateRequest:
    admin_telegram_id: int
    key: str
    value: str
    confirm: bool = False


@dataclass(frozen=True)
class AccountDeletionRequest:
    telegram_id: int
    confirm: bool = False


@dataclass(frozen=True)
class UserProfileDTO:
    telegram_id: int
    university_id: str
    department_id: str | None
    section: str | None
    campus: str | None = None


@dataclass(frozen=True)
class MetricsSnapshot:
    uptime_seconds: int
    scrape_attempts: int = 0
    scrape_failures: int = 0
    active_users: int = 0
    cache_hit_rate: float = 0.0
    details: dict[str, str] = field(default_factory=dict)
