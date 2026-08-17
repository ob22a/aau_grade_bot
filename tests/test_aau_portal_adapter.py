"""Unit tests for AAU portal adapter client."""

from __future__ import annotations

import pytest
from pathlib import Path

from clients.aau_portal_adapter import AAUPortalClient
from clients.aau_portal import (
    PortalAuthenticationError,
    PortalLockoutRiskError,
    PortalSchemaChangedError,
    PortalDataValidationError,
)
from config import Settings


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def settings():
    """Application settings for adapter."""
    return Settings(
        portal_timeout_seconds=30,
        portal_semaphore_limit=5,
    )


@pytest.fixture
def adapter(settings):
    """AAU portal adapter instance."""
    return AAUPortalClient(settings)


def _read_fixture(filename: str) -> str:
    """Load HTML fixture from tests/fixtures/portal/."""
    return (Path("tests/fixtures/portal") / filename).read_text(encoding="utf-8")


# ============================================================================
# STUDENT ID VALIDATION
# ============================================================================


class TestStudentIdValidation:
    """Student ID format validation tests."""

    def test_valid_student_id_format(self, adapter):
        """Valid UGR/NNNN/YY format should not raise."""
        adapter._validate_student_id("UGR/0123/45")
        adapter._validate_student_id("UGR/9999/99")

    def test_valid_student_id_case_insensitive(self, adapter):
        """Student ID validation should accept mixed case."""
        adapter._validate_student_id("ugr/0123/45")
        adapter._validate_student_id("Ugr/5678/90")

    def test_invalid_student_id_missing_prefix(self, adapter):
        """Missing UGR prefix should raise."""
        with pytest.raises(PortalDataValidationError, match="Invalid student ID format"):
            adapter._validate_student_id("0123/45")

    def test_invalid_student_id_wrong_number_digits(self, adapter):
        """Wrong digit counts should raise."""
        with pytest.raises(PortalDataValidationError, match="Invalid student ID format"):
            adapter._validate_student_id("UGR/123/45")  # Only 3 digits instead of 4

        with pytest.raises(PortalDataValidationError, match="Invalid student ID format"):
            adapter._validate_student_id("UGR/01234/45")  # 5 digits instead of 4

    def test_invalid_student_id_missing_year(self, adapter):
        """Missing year suffix should raise."""
        with pytest.raises(PortalDataValidationError, match="Invalid student ID format"):
            adapter._validate_student_id("UGR/0123")

    def test_invalid_student_id_wrong_year_digits(self, adapter):
        """Wrong year digit count should raise."""
        with pytest.raises(PortalDataValidationError, match="Invalid student ID format"):
            adapter._validate_student_id("UGR/0123/5")  # Only 1 digit for year

        with pytest.raises(PortalDataValidationError, match="Invalid student ID format"):
            adapter._validate_student_id("UGR/0123/456")  # 3 digits for year


# ============================================================================
# TOKEN EXTRACTION
# ============================================================================


class TestTokenExtraction:
    """RequestVerificationToken extraction tests."""

    def test_extract_token_from_valid_login_page(self, adapter):
        """Extract token from standard login page form."""
        html = _read_fixture("login.html")
        # Manually test the token extraction logic
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        token_input = soup.find("input", {"name": "__RequestVerificationToken"})

        assert token_input is not None, "Token input should exist"
        assert token_input.get("value") == "SANITISED_TEST_TOKEN"

    def test_login_page_has_correct_fields(self, adapter):
        """Login page should have all required form fields."""
        html = _read_fixture("login.html")
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        form = soup.find("form", {"action": "/login"})

        assert form is not None, "Login form should exist"

        # Check all required inputs
        username_input = form.find("input", {"name": "UserName"})
        password_input = form.find("input", {"name": "Password"})
        token_input = form.find("input", {"name": "__RequestVerificationToken"})

        assert username_input is not None
        assert password_input is not None
        assert token_input is not None


# ============================================================================
# LOGIN RESPONSE CLASSIFICATION
# ============================================================================


class TestLoginClassification:
    """Login response classification tests."""

    def test_classify_successful_login(self, adapter):
        """No login form = SUCCESS."""
        # A successful login redirects or returns the dashboard without the login form
        html = "<html><body><h1>Dashboard</h1></body></html>"
        result = adapter._classify_login_response(html)

        assert result["status"] == "SUCCESS"
        assert "html" in result

    def test_classify_invalid_credentials(self, adapter):
        """'Incorrect username or password' = INVALID_CREDENTIALS."""
        html = _read_fixture("login_invalid_credentials.html")
        result = adapter._classify_login_response(html)

        assert result["status"] == "INVALID_CREDENTIALS"
        assert "html" in result

    def test_classify_lockout_risk_three_attempts(self, adapter):
        """'N more attempt(s)' with N <= 3 = LOCKOUT_RISK."""
        html = _read_fixture("login_lockout_risk.html")
        result = adapter._classify_login_response(html)

        assert result["status"] == "LOCKOUT_RISK"
        assert result["attempts_remaining"] == 3
        assert "html" in result

    def test_classify_lockout_risk_single_attempt(self, adapter):
        """Single remaining attempt should trigger LOCKOUT_RISK."""
        html_template = """
        <form action="/login" method="post">
          <input name="__RequestVerificationToken" type="hidden" value="TOKEN" />
          <div class="validation-summary-errors">
            <ul><li>Invalid credentials. You have 1 more attempt(s) before your account gets locked out.</li></ul>
          </div>
        </form>
        """
        result = adapter._classify_login_response(html_template)

        assert result["status"] == "LOCKOUT_RISK"
        assert result["attempts_remaining"] == 1

    def test_classify_lockout_risk_many_attempts(self, adapter):
        """Many remaining attempts should NOT trigger LOCKOUT_RISK."""
        html_template = """
        <form action="/login" method="post">
          <input name="__RequestVerificationToken" type="hidden" value="TOKEN" />
          <div class="validation-summary-errors">
            <ul><li>Invalid credentials. You have 10 more attempt(s) before your account gets locked out.</li></ul>
          </div>
        </form>
        """
        result = adapter._classify_login_response(html_template)

        # With many attempts, should fall through to generic INVALID_CREDENTIALS
        assert result["status"] == "INVALID_CREDENTIALS"


# ============================================================================
# AUTH FAILURE HANDLING
# ============================================================================


class TestAuthFailureHandling:
    """Authentication failure exception raising tests."""

    def test_handle_invalid_credentials_raises(self, adapter):
        """INVALID_CREDENTIALS should raise PortalAuthenticationError."""
        auth_result = {"status": "INVALID_CREDENTIALS", "html": "<html></html>"}

        with pytest.raises(PortalAuthenticationError, match="invalid credentials"):
            adapter._handle_auth_failure(auth_result)

    def test_handle_lockout_risk_raises(self, adapter):
        """LOCKOUT_RISK should raise PortalLockoutRiskError with attempts."""
        auth_result = {
            "status": "LOCKOUT_RISK",
            "html": "<html></html>",
            "attempts_remaining": 2,
        }

        with pytest.raises(PortalLockoutRiskError, match="2 attempt"):
            adapter._handle_auth_failure(auth_result)


# ============================================================================
# ADAPTER INITIALIZATION
# ============================================================================


class TestAdapterInitialization:
    """Adapter configuration and initialization tests."""

    def test_adapter_init_with_valid_settings(self, settings):
        """Adapter should initialize with valid settings."""
        adapter = AAUPortalClient(settings)

        assert adapter.settings == settings
        assert adapter.semaphore._value == 5

    def test_adapter_init_invalid_semaphore_limit(self, settings):
        """Zero or negative semaphore limit should raise."""
        settings.portal_semaphore_limit = 0

        with pytest.raises(ValueError, match="semaphore_limit must be >= 1"):
            AAUPortalClient(settings)

    def test_adapter_constants(self):
        """Adapter should have correct endpoint constants."""
        assert AAUPortalClient.BASE_URL == "https://portal.aau.edu.et"
        assert AAUPortalClient.LOGIN_ENDPOINT == "/login"
        assert AAUPortalClient.HOME_ENDPOINT == "/Home"
        assert AAUPortalClient.GRADES_ENDPOINT == "/Grade/GradeReport"
        assert AAUPortalClient.ASSESSMENT_ENDPOINT == "/Grade/GradeReport/AssessmentDetail"


# ============================================================================
# STUDENT ID PATTERN REGEX
# ============================================================================


class TestStudentIdPattern:
    """Student ID regex pattern tests."""

    def test_pattern_matches_valid_ids(self):
        """Regex should match valid UGR/NNNN/YY format."""
        pattern = AAUPortalClient.STUDENT_ID_PATTERN

        assert pattern.match("UGR/0000/00")
        assert pattern.match("UGR/9999/99")
        assert pattern.match("UGR/1234/56")

    def test_pattern_matches_case_insensitive(self):
        """Regex should be case-insensitive."""
        pattern = AAUPortalClient.STUDENT_ID_PATTERN

        assert pattern.match("ugr/0000/00")
        assert pattern.match("UgR/1234/56")

    def test_pattern_rejects_invalid_formats(self):
        """Regex should not match invalid formats."""
        pattern = AAUPortalClient.STUDENT_ID_PATTERN

        assert not pattern.match("UGR/000/00")  # 3 digits
        assert not pattern.match("UGR/00000/00")  # 5 digits
        assert not pattern.match("UGR/0000/0")  # 1 digit year
        assert not pattern.match("UGR/0000/000")  # 3 digit year
        assert not pattern.match("0000/0000/00")  # Wrong prefix
        assert not pattern.match("UGR0000/00")  # Missing slash
