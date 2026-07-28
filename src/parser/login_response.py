"""Classification of AAU login responses without relying on HTTP status alone."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from bs4 import BeautifulSoup


class LoginStatus(str, Enum):
    """Safe outcomes exposed by the portal client."""

    AUTHENTICATED = "authenticated"
    INVALID_CREDENTIALS = "invalid_credentials"
    LOCKOUT_RISK = "lockout_risk"
    UNKNOWN_LOGIN_RESPONSE = "unknown_login_response"


@dataclass(frozen=True, slots=True)
class LoginResponse:
    status: LoginStatus
    remaining_attempts: int | None = None


_ATTEMPTS_PATTERN = re.compile(r"\b(\d+)\s+more\s+attempt\(s\)", re.IGNORECASE)
_INVALID_CREDENTIAL_MARKERS = ("incorrect username or password", "invalid credentials")
LOCKOUT_RISK_THRESHOLD = 3


def classify_login_response(html: str) -> LoginResponse:
    """Classify AAU's login HTML.

    AAU returns HTTP 200 for failed authentication, so callers must invoke this
    before considering a response authenticated. Unknown login-form responses
    remain unsafe to retry and are surfaced distinctly for alerting.
    """
    document = BeautifulSoup(html, "html.parser")
    validation_summary = document.select_one("div.validation-summary-errors")
    message = (
        validation_summary.get_text(" ", strip=True).casefold()
        if validation_summary is not None
        else ""
    )

    if any(marker in message for marker in _INVALID_CREDENTIAL_MARKERS):
        attempts_match = _ATTEMPTS_PATTERN.search(message)
        remaining_attempts = int(attempts_match.group(1)) if attempts_match else None
        status = (
            LoginStatus.LOCKOUT_RISK
            if remaining_attempts is not None and remaining_attempts <= LOCKOUT_RISK_THRESHOLD
            else LoginStatus.INVALID_CREDENTIALS
        )
        return LoginResponse(status=status, remaining_attempts=remaining_attempts)

    if document.select_one('form[action="/login"] input[name="__RequestVerificationToken"]'):
        return LoginResponse(status=LoginStatus.UNKNOWN_LOGIN_RESPONSE)

    return LoginResponse(status=LoginStatus.AUTHENTICATED)
