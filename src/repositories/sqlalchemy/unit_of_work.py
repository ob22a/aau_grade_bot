"""Repository unit of work for SQLAlchemy-backed persistence."""

from __future__ import annotations

from collections.abc import Callable
from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession

from database.unit_of_work import SqlAlchemyUnitOfWork as BaseUnitOfWork
from .audit_repository import SqlAlchemyAuditLogRepository
from .cron_run_repository import SqlAlchemyCronRunRepository
from .credential_repository import SqlAlchemyUserCredentialRepository
from .system_setting_repository import SqlAlchemySystemSettingRepository
from .user_repository import SqlAlchemyUserRepository
from .user_course_repository import SqlAlchemyUserCourseRepository
from .assessment_repository import SqlAlchemyAssessmentRepository
from .semester_result_repository import SqlAlchemySemesterResultRepository
from .campus_repository import SqlAlchemyCampusRepository
from .department_repository import SqlAlchemyDepartmentRepository
from .course_repository import SqlAlchemyCourseRepository
from .admin_repository import SqlAlchemyAdminRepository

SessionFactory = Callable[[], AsyncSession]


class SqlAlchemyRepositoryUnitOfWork:
    """Unit of work exposing SQLAlchemy repositories."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._base_uow = BaseUnitOfWork(session_factory)
        self.session: AsyncSession | None = None
        self.users: SqlAlchemyUserRepository | None = None
        self.campuses: SqlAlchemyCampusRepository | None = None
        self.credentials: SqlAlchemyUserCredentialRepository | None = None
        self.audit_logs: SqlAlchemyAuditLogRepository | None = None
        self.settings: SqlAlchemySystemSettingRepository | None = None
        self.cron_runs: SqlAlchemyCronRunRepository | None = None
        self.user_courses: SqlAlchemyUserCourseRepository | None = None
        self.assessments: SqlAlchemyAssessmentRepository | None = None
        self.semester_results: SqlAlchemySemesterResultRepository | None = None
        self.departments: SqlAlchemyDepartmentRepository | None = None
        self.courses: SqlAlchemyCourseRepository | None = None
        self.admin: SqlAlchemyAdminRepository | None = None

    async def __aenter__(self) -> Self:
        await self._base_uow.__aenter__()
        self.session = self._base_uow.session
        if self.session is None:
            raise RuntimeError("Failed to initialize SQLAlchemy session")

        self.users = SqlAlchemyUserRepository(self.session)
        self.campuses = SqlAlchemyCampusRepository(self.session)
        self.credentials = SqlAlchemyUserCredentialRepository(self.session)
        self.audit_logs = SqlAlchemyAuditLogRepository(self.session)
        self.settings = SqlAlchemySystemSettingRepository(self.session)
        self.cron_runs = SqlAlchemyCronRunRepository(self.session)
        self.user_courses = SqlAlchemyUserCourseRepository(self.session)
        self.assessments = SqlAlchemyAssessmentRepository(self.session)
        self.semester_results = SqlAlchemySemesterResultRepository(self.session)
        self.departments = SqlAlchemyDepartmentRepository(self.session)
        self.courses = SqlAlchemyCourseRepository(self.session)
        self.admin = SqlAlchemyAdminRepository(self.session)

        return self

    async def commit(self) -> None:
        await self._base_uow.commit()

    async def rollback(self) -> None:
        await self._base_uow.rollback()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self._base_uow.__aexit__(exc_type, exc, traceback)
        self.session = None
        self.users = None
        self.campuses = None
        self.credentials = None
        self.audit_logs = None
        self.settings = None
        self.cron_runs = None
        self.user_courses = None
        self.assessments = None
        self.semester_results = None
        self.departments = None
        self.courses = None
