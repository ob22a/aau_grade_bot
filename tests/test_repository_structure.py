"""Basic structure tests for repository and database packages."""

from repositories.sqlalchemy import (
    SqlAlchemyRepositoryUnitOfWork,
    SqlAlchemyUserRepository,
    SqlAlchemyUserCredentialRepository,
    SqlAlchemyAuditLogRepository,
    SqlAlchemySystemSettingRepository,
    SqlAlchemyCronRunRepository,
    SqlAlchemyUserCourseRepository,
    SqlAlchemyAssessmentRepository,
    SqlAlchemySemesterResultRepository,
)

from database.connection import (
    create_engine_from_url,
    create_session_factory,
    clean_async_database_url,
)
from database.models import Base


def test_repository_unit_of_work_has_all_repositories() -> None:
    uow = SqlAlchemyRepositoryUnitOfWork(lambda: None)  # type: ignore[arg-type]

    assert hasattr(uow, "users")
    assert hasattr(uow, "credentials")
    assert hasattr(uow, "audit_logs")
    assert hasattr(uow, "settings")
    assert hasattr(uow, "cron_runs")
    assert hasattr(uow, "user_courses")
    assert hasattr(uow, "assessments")
    assert hasattr(uow, "semester_results")


def test_database_package_exports_are_available() -> None:
    assert create_engine_from_url is not None
    assert create_session_factory is not None
    assert clean_async_database_url is not None
    assert Base is not None


def test_clean_async_database_url_rewrites_postgres_scheme() -> None:
    rewritten = clean_async_database_url("postgres://user:pass@localhost/db")
    assert rewritten.startswith("postgresql+asyncpg://")
    assert "sslmode" not in rewritten
