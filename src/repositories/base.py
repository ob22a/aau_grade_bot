from __future__ import annotations

from types import TracebackType
from typing import Protocol, runtime_checkable


class Repository(Protocol):
    """A repository is a persistence boundary implementation."""
    ...


class UnitOfWork(Protocol):
    users: UserRepository
    campuses: CampusRepository
    credentials: UserCredentialRepository
    audit_logs: AuditLogRepository
    settings: SystemSettingRepository
    cron_runs: CronRunRepository
    user_courses: UserCourseRepository
    assessments: AssessmentRepository
    semester_results: SemesterResultRepository
    departments: DepartmentRepository
    courses: CourseRepository
    admin: AdminRepository

    async def __aenter__(self) -> UnitOfWork:
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        ...

    async def commit(self) -> None:
        ...

    async def rollback(self) -> None:
        ...


class UserRepository(Repository, Protocol):
    async def get_by_id(self, user_id: str) -> object | None:
        ...

    async def get_by_telegram_id(self, telegram_id: int) -> object | None:
        ...

    async def get_by_university_id(self, university_id: str) -> object | None:
        ...

    async def add(self, user: object) -> None:
        ...

    async def remove(self, user: object) -> None:
        ...

    async def get_all_users(self) -> list[object]:
        ...

class CampusRepository(Repository, Protocol):
    async def get_all(self) -> list[object]:
        ...

class DepartmentRepository(Repository, Protocol):
    async def get_by_id(self, department_id: str) -> object | None:
        ...

    async def get_by_name(self, full_name: str) -> object | None:
        ...

    async def add(self, department: object) -> None:
        ...

class CourseRepository(Repository, Protocol):
    async def get_by_id(self, course_id: str) -> object | None:
        ...

    async def add(self, course: object) -> None:
        ...

class UserCredentialRepository(Repository, Protocol):
    async def get_by_user_id(self, user_id: str) -> object | None:
        ...

    async def add(self, credential: object) -> None:
        ...

    async def remove_by_user_id(self, user_id: str) -> None:
        ...


class UserCourseRepository(Repository, Protocol):
    async def get_by_user_id(self, user_id: str) -> list[object]:
        ...

    async def add(self, user_course: object) -> None:
        ...

    async def remove(self, user_course: object) -> None:
        ...


class AssessmentRepository(Repository, Protocol):
    async def get_by_user_course_id(self, user_course_id: str) -> object | None:
        ...

    async def add(self, assessment: object) -> None:
        ...

    async def remove_by_user_course_id(self, user_course_id: str) -> None:
        ...


class SemesterResultRepository(Repository, Protocol):
    async def get_by_user_id(self, user_id: str) -> list[object]:
        ...

    async def add(self, semester_result: object) -> None:
        ...

    async def remove(self, semester_result: object) -> None:
        ...


class AuditLogRepository(Repository, Protocol):
    async def add(self, audit_log: object) -> None:
        ...


class SystemSettingRepository(Repository, Protocol):
    async def get(self, key: str) -> str | None:
        ...

    async def set(self, key: str, value: str) -> None:
        ...


class CronRunRepository(Repository, Protocol):
    async def add(self, cron_run: object) -> None:
        ...

    async def get_by_id(self, run_id: str) -> object | None:
        ...


class AdminRepository(Repository, Protocol):
    async def get_system_metrics(self) -> dict:
        ...

