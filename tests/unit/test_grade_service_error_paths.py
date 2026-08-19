"""Unit tests for GradeReadService error paths and edge cases.

These tests verify that the grade service handles failures gracefully:
- Corrupt cache data
- Portal scrape failures
- DB query failures
- Missing credentials
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dto.bot import GradeReadRequest, GradeReadResult
from services.grades.service import GradeReadService


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


class TestDatabaseErrorPaths:
    def test_corrupt_json_in_db_skips_report(self) -> None:
        """When DB encrypted detail is not valid JSON, it skips the report."""
        from crypto.cipher import AesGcmCipher
        cipher = AesGcmCipher.from_base64_key(AesGcmCipher.generate_key())
        
        mock_user = SimpleNamespace(id="user-1", telegram_id=123, university_id="UGR/1234/16")
        mock_db_result = SimpleNamespace(
            user_id="user-1",
            encrypted_result_detail=cipher.encrypt("this is not json {{{")
        )

        mock_uow = AsyncMock()
        mock_uow.__aenter__ = AsyncMock(return_value=mock_uow)
        mock_uow.__aexit__ = AsyncMock(return_value=False)
        mock_uow.users = AsyncMock()
        mock_uow.users.get_by_telegram_id = AsyncMock(return_value=mock_user)
        mock_uow.session = AsyncMock()
        mock_uow.session.scalars = AsyncMock(return_value=[mock_db_result])

        with patch("repositories.sqlalchemy.unit_of_work.SqlAlchemyRepositoryUnitOfWork", return_value=mock_uow):
            service = GradeReadService(cipher=cipher, session_factory=MagicMock())
            result = _run(service.read(GradeReadRequest(telegram_id=123, page_index=0)))

        assert result.cached is False
        assert "No grades available" in result.message

    def test_force_refresh_honors_cooldown(self) -> None:
        """When force_refresh=True and cooldown is active, fallback to DB."""
        cache = AsyncMock()
        cache.get = AsyncMock(return_value="1")  # cooldown active

        from crypto.cipher import AesGcmCipher
        cipher = AesGcmCipher.from_base64_key(AesGcmCipher.generate_key())
        
        mock_user = SimpleNamespace(id="user-1", telegram_id=123, university_id="UGR/1234/16")
        mock_uow = AsyncMock()
        mock_uow.__aenter__ = AsyncMock(return_value=mock_uow)
        mock_uow.__aexit__ = AsyncMock(return_value=False)
        mock_uow.users = AsyncMock()
        mock_uow.users.get_by_telegram_id = AsyncMock(return_value=mock_user)
        mock_uow.session = AsyncMock()
        mock_uow.session.scalars = AsyncMock(return_value=[])

        with patch("repositories.sqlalchemy.unit_of_work.SqlAlchemyRepositoryUnitOfWork", return_value=mock_uow):
            service = GradeReadService(cache=cache, cipher=cipher, session_factory=MagicMock())
            result = _run(
                service.read(GradeReadRequest(telegram_id=123, page_index=0, force_refresh=True))
            )

        cache.get.assert_any_call("cooldown:scrape:123")
        assert "No grades available" in result.message


class TestPortalScrapeErrorPaths:
    def test_portal_scrape_timeout_returns_fallback(self) -> None:
        """When portal scrape raises an exception, return fallback gracefully."""
        portal = AsyncMock()
        portal.scrape = AsyncMock(side_effect=TimeoutError("Portal timed out"))

        from crypto.cipher import AesGcmCipher

        cipher = AesGcmCipher.from_base64_key(AesGcmCipher.generate_key())

        # Simulate a DB user with credentials
        mock_user = SimpleNamespace(id="user-1", telegram_id=456, university_id="UGR/1234/16")
        mock_cred = SimpleNamespace(
            user_id="user-1",
            encrypted_password=cipher.encrypt("password123"),
        )

        mock_uow = AsyncMock()
        mock_uow.__aenter__ = AsyncMock(return_value=mock_uow)
        mock_uow.__aexit__ = AsyncMock(return_value=False)
        mock_uow.users = AsyncMock()
        mock_uow.users.get_by_telegram_id = AsyncMock(return_value=mock_user)
        mock_uow.credentials = AsyncMock()
        mock_uow.credentials.get_by_user_id = AsyncMock(return_value=mock_cred)

        # Patch at the import location used inside the service
        with patch(
            "repositories.sqlalchemy.unit_of_work.SqlAlchemyRepositoryUnitOfWork",
            return_value=mock_uow,
        ):
            service = GradeReadService(
                portal_client=portal,
                cipher=cipher,
                session_factory=MagicMock(),
            )
            result = _run(service.read(GradeReadRequest(telegram_id=456, page_index=0)))

        # Should not crash — should return fallback
        assert result.cached is False
        assert "No grades available" in result.message

    def test_portal_returns_empty_grades(self) -> None:
        """When portal returns no grade reports, return fallback."""
        from crypto.cipher import AesGcmCipher
        from parser.models import ProfilePageResult, StudentProfileData

        cipher = AesGcmCipher.from_base64_key(AesGcmCipher.generate_key())

        mock_profile = ProfilePageResult(
            profile=StudentProfileData(
                full_name="Test",
                student_id="UGR/1234/16",
                department="CS",
                year_level="Year III",
            )
        )

        portal = AsyncMock()
        portal.scrape = AsyncMock(return_value=(mock_profile, None))

        mock_user = SimpleNamespace(id="user-1", telegram_id=789, university_id="UGR/1234/16")
        mock_cred = SimpleNamespace(
            user_id="user-1",
            encrypted_password=cipher.encrypt("pass"),
        )

        mock_uow = AsyncMock()
        mock_uow.__aenter__ = AsyncMock(return_value=mock_uow)
        mock_uow.__aexit__ = AsyncMock(return_value=False)
        mock_uow.users = AsyncMock()
        mock_uow.users.get_by_telegram_id = AsyncMock(return_value=mock_user)
        mock_uow.credentials = AsyncMock()
        mock_uow.credentials.get_by_user_id = AsyncMock(return_value=mock_cred)

        with patch(
            "repositories.sqlalchemy.unit_of_work.SqlAlchemyRepositoryUnitOfWork",
            return_value=mock_uow,
        ):
            service = GradeReadService(
                portal_client=portal,
                cipher=cipher,
                session_factory=MagicMock(),
            )
            result = _run(service.read(GradeReadRequest(telegram_id=789, page_index=0)))

        assert "No grades available" in result.message


class TestDBErrorPaths:
    def test_db_connection_failure_returns_fallback(self) -> None:
        """When the DB is unreachable, return fallback without crashing."""
        from crypto.cipher import AesGcmCipher

        cipher = AesGcmCipher.from_base64_key(AesGcmCipher.generate_key())

        with patch(
            "repositories.sqlalchemy.unit_of_work.SqlAlchemyRepositoryUnitOfWork",
            side_effect=ConnectionError("DB down"),
        ):
            service = GradeReadService(
                cipher=cipher,
                session_factory=MagicMock(),
            )
            result = _run(service.read(GradeReadRequest(telegram_id=100, page_index=0)))

        assert result.cached is False
        assert "No grades available" in result.message

    def test_user_not_found_in_db(self) -> None:
        """When user doesn't exist in DB, return fallback."""
        from crypto.cipher import AesGcmCipher

        cipher = AesGcmCipher.from_base64_key(AesGcmCipher.generate_key())

        mock_uow = AsyncMock()
        mock_uow.__aenter__ = AsyncMock(return_value=mock_uow)
        mock_uow.__aexit__ = AsyncMock(return_value=False)
        mock_uow.users = AsyncMock()
        mock_uow.users.get_by_telegram_id = AsyncMock(return_value=None)

        with patch(
            "repositories.sqlalchemy.unit_of_work.SqlAlchemyRepositoryUnitOfWork",
            return_value=mock_uow,
        ):
            service = GradeReadService(
                cipher=cipher,
                session_factory=MagicMock(),
            )
            result = _run(service.read(GradeReadRequest(telegram_id=999, page_index=0)))

        assert "No grades available" in result.message


class TestPaginationEdgeCases:
    def test_page_index_out_of_bounds_clamped(self) -> None:
        """When page_index exceeds total pages, clamp to last page."""
        from crypto.cipher import AesGcmCipher
        from parser.models import GradeReport, GradeReportSummary
        cipher = AesGcmCipher.from_base64_key(AesGcmCipher.generate_key())
        
        rep1 = GradeReport(warnings=(), academic_year="1", year_label="1", semester_label="One", course_grades=(), summary=GradeReportSummary(sgp=0, sgpa=0, cgp=0, cgpa=0, academic_status=""))
        rep2 = GradeReport(warnings=(), academic_year="1", year_label="1", semester_label="Two", course_grades=(), summary=GradeReportSummary(sgp=0, sgpa=0, cgp=0, cgpa=0, academic_status=""))

        mock_user = SimpleNamespace(id="user-1", telegram_id=123, university_id="UGR/1234/16")
        mock_uow = AsyncMock()
        mock_uow.__aenter__ = AsyncMock(return_value=mock_uow)
        mock_uow.__aexit__ = AsyncMock(return_value=False)
        mock_uow.users = AsyncMock()
        mock_uow.users.get_by_telegram_id = AsyncMock(return_value=mock_user)
        mock_uow.session = AsyncMock()
        mock_uow.session.scalars = AsyncMock(return_value=[
            SimpleNamespace(user_id="user-1", encrypted_result_detail=cipher.encrypt(json.dumps(rep1.model_dump()))),
            SimpleNamespace(user_id="user-1", encrypted_result_detail=cipher.encrypt(json.dumps(rep2.model_dump()))),
        ])

        with patch("repositories.sqlalchemy.unit_of_work.SqlAlchemyRepositoryUnitOfWork", return_value=mock_uow):
            service = GradeReadService(cipher=cipher, session_factory=MagicMock())
            result = _run(service.read(GradeReadRequest(telegram_id=123, page_index=99)))

        assert result.current_page == 1  # clamped to last page
        assert result.total_pages == 2
        assert "Two" in result.message

    def test_negative_page_index_clamped(self) -> None:
        """When page_index is negative, clamp to 0."""
        from crypto.cipher import AesGcmCipher
        from parser.models import GradeReport, GradeReportSummary
        cipher = AesGcmCipher.from_base64_key(AesGcmCipher.generate_key())
        
        rep1 = GradeReport(warnings=(), academic_year="1", year_label="1", semester_label="One", course_grades=(), summary=GradeReportSummary(sgp=0, sgpa=0, cgp=0, cgpa=0, academic_status=""))
        rep2 = GradeReport(warnings=(), academic_year="1", year_label="1", semester_label="Two", course_grades=(), summary=GradeReportSummary(sgp=0, sgpa=0, cgp=0, cgpa=0, academic_status=""))

        mock_user = SimpleNamespace(id="user-1", telegram_id=123, university_id="UGR/1234/16")
        mock_uow = AsyncMock()
        mock_uow.__aenter__ = AsyncMock(return_value=mock_uow)
        mock_uow.__aexit__ = AsyncMock(return_value=False)
        mock_uow.users = AsyncMock()
        mock_uow.users.get_by_telegram_id = AsyncMock(return_value=mock_user)
        mock_uow.session = AsyncMock()
        mock_uow.session.scalars = AsyncMock(return_value=[
            SimpleNamespace(user_id="user-1", encrypted_result_detail=cipher.encrypt(json.dumps(rep1.model_dump()))),
            SimpleNamespace(user_id="user-1", encrypted_result_detail=cipher.encrypt(json.dumps(rep2.model_dump()))),
        ])

        with patch("repositories.sqlalchemy.unit_of_work.SqlAlchemyRepositoryUnitOfWork", return_value=mock_uow):
            service = GradeReadService(cipher=cipher, session_factory=MagicMock())
            result = _run(service.read(GradeReadRequest(telegram_id=123, page_index=-5)))

        assert result.current_page == 0
        assert "One" in result.message
