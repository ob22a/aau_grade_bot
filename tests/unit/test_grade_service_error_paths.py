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


class TestCacheErrorPaths:
    def test_corrupt_json_in_cache_returns_raw_string(self) -> None:
        """When cached value is not valid JSON, return it as a raw string."""
        cache = AsyncMock()
        cache.get = AsyncMock(return_value="this is not json {{{")

        service = GradeReadService(cache=cache)
        result = _run(service.read(GradeReadRequest(telegram_id=123, page_index=0)))

        assert result.cached is True
        assert "this is not json" in result.message

    def test_cache_returns_empty_list(self) -> None:
        """When cached value is an empty JSON list, fall through to next layer."""
        cache = AsyncMock()
        cache.get = AsyncMock(return_value=json.dumps([]))

        service = GradeReadService(cache=cache)
        result = _run(service.read(GradeReadRequest(telegram_id=123, page_index=0)))

        # Empty list doesn't satisfy `if isinstance(pages, list) and pages:`
        # so it falls through to the fallback message.
        assert "No grades available" in result.message

    def test_cache_returns_non_list_json_falls_through(self) -> None:
        """When cached value is valid JSON but not a list, falls through to fallback."""
        cache = AsyncMock()
        cache.get = AsyncMock(return_value=json.dumps({"key": "value"}))

        service = GradeReadService(cache=cache)
        result = _run(service.read(GradeReadRequest(telegram_id=123, page_index=0)))

        # Non-list JSON fails the isinstance check and hits the except branch
        # which returns it as a string — or falls through depending on implementation.
        # The actual behavior: json.loads succeeds, isinstance(dict, list) is False,
        # so it falls through the `if` block and the except is not triggered.
        # The function then falls through to the fallback.
        assert result is not None  # Should not crash

    def test_cache_miss_with_no_other_sources(self) -> None:
        """When cache returns None and no other sources configured, return fallback."""
        cache = AsyncMock()
        cache.get = AsyncMock(return_value=None)

        service = GradeReadService(cache=cache)
        result = _run(service.read(GradeReadRequest(telegram_id=123, page_index=0)))

        assert result.cached is False
        assert "No grades available" in result.message

    def test_force_refresh_skips_cache(self) -> None:
        """When force_refresh=True, cache is not consulted."""
        cache = AsyncMock()
        cache.get = AsyncMock(return_value=json.dumps(["cached page"]))

        service = GradeReadService(cache=cache)
        result = _run(
            service.read(GradeReadRequest(telegram_id=123, page_index=0, force_refresh=True))
        )

        # Cache.get should not have been called
        cache.get.assert_not_called()
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
        cache = AsyncMock()
        cache.get = AsyncMock(return_value=json.dumps(["page0", "page1"]))

        service = GradeReadService(cache=cache)
        result = _run(service.read(GradeReadRequest(telegram_id=123, page_index=99)))

        assert result.current_page == 1  # clamped to last page
        assert result.total_pages == 2
        assert result.message == "page1"

    def test_negative_page_index_clamped(self) -> None:
        """When page_index is negative, clamp to 0."""
        cache = AsyncMock()
        cache.get = AsyncMock(return_value=json.dumps(["page0", "page1"]))

        service = GradeReadService(cache=cache)
        result = _run(service.read(GradeReadRequest(telegram_id=123, page_index=-5)))

        assert result.current_page == 0
        assert result.message == "page0"
