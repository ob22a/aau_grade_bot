"""Unit tests for database connection configuration.

Validates that the engine factory produces the correct pool type, statement cache
settings, and health-check parameters depending on whether the URL is a Neon
pooler endpoint or a direct connection.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from database.connection import (
    _is_pooler_url,
    clean_async_database_url,
    create_engine_from_url,
)


# ---------------------------------------------------------------------------
# _is_pooler_url detection
# ---------------------------------------------------------------------------


class TestIsPoolerUrl:
    def test_detects_neon_pooler_hostname(self) -> None:
        url = "postgresql+asyncpg://user:pass@ep-cool-wind-123456-pooler.us-east-1.aws.neon.tech/neondb"
        assert _is_pooler_url(url) is True

    def test_rejects_direct_neon_hostname(self) -> None:
        url = "postgresql+asyncpg://user:pass@ep-cool-wind-123456.us-east-1.aws.neon.tech/neondb"
        assert _is_pooler_url(url) is False

    def test_rejects_localhost(self) -> None:
        assert _is_pooler_url("postgresql+asyncpg://user:pass@localhost/testdb") is False

    def test_handles_empty_hostname(self) -> None:
        assert _is_pooler_url("postgresql+asyncpg:///testdb") is False


# ---------------------------------------------------------------------------
# clean_async_database_url
# ---------------------------------------------------------------------------


class TestCleanAsyncDatabaseUrl:
    def test_converts_postgres_scheme(self) -> None:
        url = "postgres://user:pass@host/db"
        result = clean_async_database_url(url)
        assert result is not None
        assert result.startswith("postgresql+asyncpg://")

    def test_converts_postgresql_scheme(self) -> None:
        url = "postgresql://user:pass@host/db"
        result = clean_async_database_url(url)
        assert result is not None
        assert result.startswith("postgresql+asyncpg://")

    def test_strips_sslmode_parameter(self) -> None:
        url = "postgres://user:pass@host/db?sslmode=require"
        result = clean_async_database_url(url)
        assert result is not None
        assert "sslmode" not in result

    def test_strips_channel_binding_parameter(self) -> None:
        url = "postgres://user:pass@host/db?channel_binding=prefer"
        result = clean_async_database_url(url)
        assert result is not None
        assert "channel_binding" not in result

    def test_preserves_other_parameters(self) -> None:
        url = "postgres://user:pass@host/db?application_name=myapp&sslmode=require"
        result = clean_async_database_url(url)
        assert result is not None
        assert "application_name=myapp" in result
        assert "sslmode" not in result

    def test_returns_none_for_none(self) -> None:
        assert clean_async_database_url(None) is None

    def test_returns_empty_for_empty(self) -> None:
        result = clean_async_database_url("")
        assert not result  # falsy (empty string)


# ---------------------------------------------------------------------------
# create_engine_from_url — pool strategy
# ---------------------------------------------------------------------------


class TestCreateEnginePoolStrategy:
    """Verify the engine factory selects NullPool for pooler URLs and QueuePool for direct."""

    @patch("database.connection.create_async_engine")
    def test_pooler_url_uses_nullpool(self, mock_create: MagicMock) -> None:
        mock_create.return_value = MagicMock()
        url = "postgres://user:pass@ep-cool-wind-123456-pooler.us-east-1.aws.neon.tech/neondb"

        create_engine_from_url(url)

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args[1]

        # Must use NullPool
        from sqlalchemy.pool import NullPool
        assert call_kwargs["poolclass"] is NullPool

        # Must disable statement caching
        connect_args = call_kwargs["connect_args"]
        assert connect_args["statement_cache_size"] == 0
        assert connect_args["prepared_statement_cache_size"] == 0

        # Must NOT have pool_pre_ping or pool_recycle (meaningless with NullPool)
        assert "pool_pre_ping" not in call_kwargs
        assert "pool_recycle" not in call_kwargs

    @patch("database.connection.create_async_engine")
    def test_direct_url_uses_queuepool(self, mock_create: MagicMock) -> None:
        mock_create.return_value = MagicMock()
        url = "postgres://user:pass@ep-cool-wind-123456.us-east-1.aws.neon.tech/neondb"

        create_engine_from_url(url)

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args[1]

        # Must NOT use NullPool (default QueuePool)
        assert "poolclass" not in call_kwargs

        # Must have pool health checks
        assert call_kwargs["pool_pre_ping"] is True
        assert call_kwargs["pool_recycle"] == 300

    def test_raises_for_empty_url(self) -> None:
        with pytest.raises(ValueError, match="DATABASE_URL is required"):
            create_engine_from_url("")
