import pytest
from pathlib import Path

from parser.login_response import LoginStatus, classify_login_response


@pytest.mark.parametrize(
    ("fixture_name", "expected_status", "expected_attempts"),
    [
        ("login_invalid_credentials.html", LoginStatus.INVALID_CREDENTIALS, None),
        ("login_attempt_warning.html", LoginStatus.INVALID_CREDENTIALS, 4),
        ("login_lockout_risk.html", LoginStatus.LOCKOUT_RISK, 3),
    ],
)
def test_classifies_aau_login_failures(fixture_name, expected_status, expected_attempts):
    html = (Path("tests/fixtures/portal") / fixture_name).read_text(encoding="utf-8")
    result = classify_login_response(html)

    assert result.status is expected_status
    assert result.remaining_attempts == expected_attempts


def test_treats_a_login_form_without_a_known_error_as_unknown():
    result = classify_login_response(
        '<form action="/login"><input name="__RequestVerificationToken"></form>'
    )
    assert result.status is LoginStatus.UNKNOWN_LOGIN_RESPONSE


def test_treats_a_page_without_login_form_as_authenticated_response():
    assert classify_login_response("<main>Welcome</main>").status is LoginStatus.AUTHENTICATED
