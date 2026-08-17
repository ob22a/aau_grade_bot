from __future__ import annotations

import asyncio
import logging
import re

import aiohttp
from bs4 import BeautifulSoup

from clients.aau_portal import (
    PortalClient,
    PortalError,
    PortalSchemaChangedError,
    PortalDataValidationError,
    PortalAuthenticationError,
    PortalTimeoutError,
    PortalUnavailableError,
    PortalLockoutRiskError,
    SchemaChangeDiagnostic,
)
from config import Settings
from parser.home import parse_profile_page
from parser.portal import parse_grade_report
from parser.models import GradeReport, ProfilePageResult

logger = logging.getLogger(__name__)


class AAUPortalClient(PortalClient):
    """
    Concrete HTTP client for AAU portal with fresh login per scrape.

    Features:
    - Extracts RequestVerificationToken from login page
    - Classifies authentication outcomes (SUCCESS, INVALID_CREDENTIALS, LOCKOUT_RISK, etc.)
    - Validates student ID format (UGR/NNNN/YY)
    - Rate-limited via semaphore (configurable per settings)
    - Safe error handling with schema change diagnostics
    - Fresh login for every scrape (no session persistence)
    """

    BASE_URL = "https://portal.aau.edu.et"
    LOGIN_ENDPOINT = "/login"
    HOME_ENDPOINT = "/Home"
    GRADES_ENDPOINT = "/Grade/GradeReport"
    ASSESSMENT_ENDPOINT = "/Grade/GradeReport/AssessmentDetail"

    # Student ID validation: UGR/NNNN/YY format
    STUDENT_ID_PATTERN = re.compile(r"^UGR/\d{4}/\d{2}$", re.IGNORECASE)

    def __init__(self, settings: Settings):
        """
        Initialize portal client with configuration.

        Args:
            settings: Application settings with portal URL, timeout, semaphore limit

        Raises:
            ValueError: If semaphore limit is invalid
        """
        self.settings = settings
        self.session: aiohttp.ClientSession | None = None
        self.semaphore = asyncio.Semaphore(settings.portal_semaphore_limit)

        if settings.portal_semaphore_limit < 1:
            raise ValueError("portal_semaphore_limit must be >= 1")

        logger.info(
            "AAUPortalClient initialized",
            extra={
                "base_url": self.BASE_URL,
                "timeout_seconds": settings.portal_timeout_seconds,
                "semaphore_limit": settings.portal_semaphore_limit,
            },
        )

    async def scrape(
        self, username: str, password: str, student_id: str
    ) -> tuple[ProfilePageResult, GradeReport]:
        """
        Login and scrape student profile and grades in a fresh session.

        Flow:
        1. Validate student_id format
        2. Create HTTP session
        3. Extract RequestVerificationToken from login page
        4. POST login credentials
        5. Classify authentication result
        6. If authenticated, parse /Home and /Grade/GradeReport
        7. Validate parsed data against student_id
        8. Return immutable DTOs

        Args:
            username: AAU student username/email
            password: AAU student password (plaintext from vault decryption)
            student_id: AAU student ID for validation (UGR/NNNN/YY format)

        Returns:
            Tuple of (ProfilePageResult, GradeReportResult) with parsed data

        Raises:
            PortalAuthenticationError: Invalid credentials
            PortalLockoutRiskError: Lockout imminent (N attempts remain)
            PortalUnavailableError: Portal connection/timeout issues
            PortalSchemaChangedError: HTML structure changed
            PortalDataValidationError: Parsed data doesn't match expected student_id
        """
        async with self.semaphore:
            self._validate_student_id(student_id)

            try:
                self.session = aiohttp.ClientSession()
                logger.debug("HTTP session created for portal scrape")

                # Extract token from login page
                token = await self._fetch_verification_token()
                logger.debug("RequestVerificationToken extracted")

                # Attempt login
                auth_result = await self._login(username, password, token, student_id)
                logger.info(
                    "Portal authentication attempt",
                    extra={"result": auth_result["status"]},
                )

                if auth_result["status"] != "SUCCESS":
                    self._handle_auth_failure(auth_result)

                # Scrape profile and grades
                profile_html = await self._fetch_page(self.HOME_ENDPOINT)
                grades_html = await self._fetch_page(self.GRADES_ENDPOINT)

                logger.debug("Portal pages fetched successfully")

                # Parse with boundary layer
                profile_result = parse_profile_page(profile_html)
                grades_result = parse_grade_report(grades_html)

                logger.info("Portal scrape completed successfully")

                return profile_result, grades_result

            except (PortalError, asyncio.TimeoutError) as exc:
                logger.error(
                    "Portal scrape failed",
                    extra={"error_type": type(exc).__name__},
                    exc_info=exc,
                )
                raise
            finally:
                if self.session:
                    await self.session.close()
                    logger.debug("HTTP session closed")

    def _validate_student_id(self, student_id: str) -> None:
        """
        Validate student ID format locally.

        Args:
            student_id: Student ID in UGR/NNNN/YY format

        Raises:
            PortalDataValidationError: If format is invalid
        """
        if not self.STUDENT_ID_PATTERN.match(student_id):
            raise PortalDataValidationError(
                f"Invalid student ID format: {student_id}. "
                f"Expected UGR/NNNN/YY (4 digits, 2-digit year)"
            )

    async def _fetch_verification_token(self) -> str:
        """
        Extract __RequestVerificationToken from login page.

        Flow:
        1. Try GET /login first
        2. If not found, try GET / (root page fallback)
        3. Search for <input name="__RequestVerificationToken" ... value="...">
        4. Return token value

        Returns:
            RequestVerificationToken value

        Raises:
            PortalSchemaChangedError: If token not found in login page
            PortalUnavailableError: If request fails
        """
        for endpoint in [self.LOGIN_ENDPOINT, "/"]:
            try:
                html = await self._fetch_page(endpoint)
                soup = BeautifulSoup(html, "html.parser")

                token_input = soup.find("input", {"name": "__RequestVerificationToken"})
                if token_input and token_input.get("value"):
                    token = token_input["value"]
                    logger.debug(
                        f"RequestVerificationToken found at {endpoint}",
                        extra={"endpoint": endpoint},
                    )
                    return token

            except PortalError:
                if endpoint == self.LOGIN_ENDPOINT:
                    continue  # Try root page
                raise

        diagnostic = SchemaChangeDiagnostic(
            page_type="login",
            detected_element="login form",
            expected_selector='input[name="__RequestVerificationToken"]',
            detail="RequestVerificationToken not found in login page or root page",
        )
        raise PortalSchemaChangedError(
            "Could not extract RequestVerificationToken from login page",
            diagnostic,
        )

    async def _login(
        self, username: str, password: str, token: str, student_id: str
    ) -> dict:
        """
        POST login credentials and classify authentication result.

        Args:
            username: AAU username
            password: AAU password
            token: RequestVerificationToken from login page
            student_id: Student ID for logging/diagnostics

        Returns:
            Dict with keys:
            - status: "SUCCESS", "INVALID_CREDENTIALS", "LOCKOUT_RISK"
            - html: Response HTML
            - attempts_remaining: Number of remaining attempts (if LOCKOUT_RISK)
        """
        login_data = {
            "__RequestVerificationToken": token,
            "UserName": username,
            "Password": password,
        }

        try:
            async with self.session.post(
                f"{self.BASE_URL}{self.LOGIN_ENDPOINT}",
                data=login_data,
                timeout=aiohttp.ClientTimeout(seconds=self.settings.portal_timeout_seconds),
                allow_redirects=False,
            ) as resp:
                html = await resp.text()
                logger.debug(
                    "Login POST completed",
                    extra={
                        "status_code": resp.status,
                        "student_id": student_id,
                    },
                )

                return self._classify_login_response(html)

        except asyncio.TimeoutError as exc:
            logger.warning("Login POST timed out")
            raise PortalTimeoutError(
                f"Portal login timeout after {self.settings.portal_timeout_seconds}s"
            ) from exc
        except aiohttp.ClientError as exc:
            logger.warning("Login POST connection error")
            raise PortalUnavailableError(
                f"Portal connection error during login: {exc}"
            ) from exc

    @staticmethod
    def _classify_login_response(html: str) -> dict:
        """
        Parse login response and classify authentication outcome.

        AAU returns 200 OK for all cases, so we must inspect HTML.

        Classification:
        - SUCCESS: No validation-summary-errors div
        - INVALID_CREDENTIALS: "Incorrect username or password."
        - LOCKOUT_RISK: "Invalid credentials. You have N more attempt(s)"
          when N <= 3

        Args:
            html: Login response HTML

        Returns:
            Dict with status and details
        """
        soup = BeautifulSoup(html, "html.parser")
        errors_div = soup.find("div", class_="validation-summary-errors")

        if not errors_div:
            logger.debug("Login successful - no validation errors found")
            return {"status": "SUCCESS", "html": html}

        error_text = errors_div.get_text(strip=True)
        logger.debug(
            "Login validation error detected",
            extra={"error_snippet": error_text[:50]},
        )

        # Check for lockout risk pattern: "N more attempt(s)"
        lockout_match = re.search(
            r"(\d+)\s+more\s+attempt", error_text, re.IGNORECASE
        )
        if lockout_match:
            attempts_remaining = int(lockout_match.group(1))
            if attempts_remaining <= 3:
                logger.warning(
                    "Lockout risk detected",
                    extra={"attempts_remaining": attempts_remaining},
                )
                return {
                    "status": "LOCKOUT_RISK",
                    "html": html,
                    "attempts_remaining": attempts_remaining,
                }

        # Generic invalid credentials
        if "incorrect" in error_text.lower() or "invalid credentials" in error_text.lower():
            logger.warning("Invalid credentials detected in login response")
            return {
                "status": "INVALID_CREDENTIALS",
                "html": html,
            }

        # Unknown error - treat as invalid credentials (safe default)
        logger.warning(
            "Unknown login error classification",
            extra={"error_text": error_text[:100]},
        )
        return {
            "status": "INVALID_CREDENTIALS",
            "html": html,
        }

    @staticmethod
    def _handle_auth_failure(auth_result: dict) -> None:
        """
        Raise appropriate exception based on authentication failure type.

        Args:
            auth_result: Result dict from _classify_login_response

        Raises:
            PortalAuthenticationError: Invalid credentials (no retry)
            PortalLockoutRiskError: Lockout imminent (require cooldown)
        """
        status = auth_result["status"]

        if status == "INVALID_CREDENTIALS":
            raise PortalAuthenticationError("Portal authentication failed: invalid credentials")

        elif status == "LOCKOUT_RISK":
            attempts = auth_result.get("attempts_remaining", 0)
            raise PortalLockoutRiskError(
                f"Portal lockout risk: {attempts} attempt(s) remaining. "
                f"Account will be locked after next failed attempt."
            )

    async def _fetch_page(self, endpoint: str) -> str:
        """
        GET page from portal with timeout and error handling.

        Args:
            endpoint: Portal endpoint (e.g., "/Home", "/Grade/GradeReport")

        Returns:
            Response HTML text

        Raises:
            PortalTimeoutError: Request exceeded timeout
            PortalUnavailableError: Connection error or non-200 status
        """
        try:
            async with self.session.get(
                f"{self.BASE_URL}{endpoint}",
                timeout=aiohttp.ClientTimeout(seconds=self.settings.portal_timeout_seconds),
                allow_redirects=True,
            ) as resp:
                if resp.status != 200:
                    logger.warning(
                        f"Unexpected HTTP status fetching {endpoint}",
                        extra={"status_code": resp.status, "endpoint": endpoint},
                    )
                    raise PortalUnavailableError(
                        f"Portal returned {resp.status} for {endpoint}"
                    )

                html = await resp.text()
                logger.debug(f"Fetched {endpoint}", extra={"endpoint": endpoint})
                return html

        except asyncio.TimeoutError as exc:
            logger.warning(f"Timeout fetching {endpoint}")
            raise PortalTimeoutError(
                f"Portal timeout fetching {endpoint} after {self.settings.portal_timeout_seconds}s"
            ) from exc
        except aiohttp.ClientError as exc:
            logger.warning(f"Connection error fetching {endpoint}")
            raise PortalUnavailableError(
                f"Portal connection error fetching {endpoint}: {exc}"
            ) from exc
