from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from parser.models import GradeReport, ParsedPortalResult, ProfilePageResult


@dataclass(frozen=True)
class SchemaChangeDiagnostic:
    """Safe metadata for operational alerts when portal HTML schema changes."""

    page_type: str  # e.g., "home", "grade", "assessment"
    detected_element: str  # e.g., "profile heading"
    expected_selector: str  # e.g., "span with text 'My Profile'"
    detail: str  # Safe summary for logging/alerts (no grades or credentials)
    html_snippet: str | None = None  # Raw HTML snippet for admin debugging


class PortalError(Exception):
    """Base error type for portal boundary failures."""


class PortalUnavailableError(PortalError):
    """The portal could not be reached or returned a transient failure."""


class PortalAuthenticationError(PortalError):
    """The supplied credentials were invalid."""


class PortalLockoutRiskError(PortalAuthenticationError):
    """Authentication failed and the portal reports a lockout risk."""


class PortalSchemaChangedError(PortalError):
    """The portal HTML contract changed and parsing cannot continue safely."""

    def __init__(self, message: str, diagnostic: SchemaChangeDiagnostic | None = None):
        """Initialize with message and optional diagnostic metadata."""
        super().__init__(message)
        self.diagnostic = diagnostic


class PortalDataValidationError(PortalError):
    """Portal data is malformed or violates expected validation rules."""


class PortalTimeoutError(PortalError):
    """The portal request timed out before completing."""


class PortalClient(Protocol):
    async def scrape(
        self,
        university_id: str,
        password: str,
        student_id: str,
    ) -> tuple[ProfilePageResult, GradeReport]:
        """Scrape the portal for a single student and return stable DTOs."""
        raise NotImplementedError()
