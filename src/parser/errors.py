"""Typed, safe errors produced at the AAU portal boundary."""

from __future__ import annotations

from dataclasses import dataclass


class PortalError(Exception):
    """Base class for errors that callers can handle without framework details."""


class PortalUnavailableError(PortalError):
    """The portal could not be reached or returned a transient server failure."""


class PortalAuthenticationError(PortalError):
    """Credentials were rejected; callers must never retry automatically."""


class PortalLockoutRiskError(PortalAuthenticationError):
    """AAU reports three or fewer remaining password attempts."""


@dataclass(frozen=True, slots=True)
class SchemaChangeDiagnostic:
    """Safe context for an operational alert; contains no user or grade data."""

    page_kind: str
    expected: str
    observed_structure_fingerprint: str


class PortalSchemaChangedError(PortalError):
    """A correctness-critical AAU HTML contract is missing or ambiguous."""

    def __init__(self, diagnostic: SchemaChangeDiagnostic) -> None:
        self.diagnostic = diagnostic
        super().__init__(
            f"AAU {diagnostic.page_kind} schema changed: expected {diagnostic.expected}"
        )


class PortalDataValidationError(PortalError):
    """The expected structure exists but its data cannot safely be interpreted."""
