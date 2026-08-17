"""Shared immutable DTOs for handlers and services."""

from .bot import (
    RegistrationRequest,
    RegistrationResult,
    GradeReadRequest,
    GradeReadResult,
    BroadcastRequest,
    SettingsUpdateRequest,
    AccountDeletionRequest,
    MetricsSnapshot,
)

__all__ = [
    "RegistrationRequest",
    "RegistrationResult",
    "GradeReadRequest",
    "GradeReadResult",
    "BroadcastRequest",
    "SettingsUpdateRequest",
    "AccountDeletionRequest",
    "MetricsSnapshot",
]
