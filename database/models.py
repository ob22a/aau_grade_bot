import uuid
from enum import Enum, auto
from typing import List, Optional
from datetime import datetime

from sqlalchemy import JSON, Integer, String, ForeignKey, Text, DateTime, func, UniqueConstraint, Index
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column

class UserRole(Enum):
    USER=auto()
    ADMIN=auto()

class Semester(Enum):
    FIRST=auto()
    SECOND=auto()
    THIRD=auto()

class CronRunStatus(Enum):
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()

class CohortScanStatus(Enum):
    PENDING = auto()
    REPRESENTATIVE_CHECK = auto()
    SCANNING_USERS = auto()
    COMPLETED = auto()
    FAILED = auto()

class GradeChangeStatus(Enum):
    NO_CHANGE = auto()
    NEW_COURSE_GRADE_RELEASED=auto()
    GRADE_RELEASED=auto()
    CHANGE_DETECTED = auto()

class SectionSource(Enum):
    SCRAPED = auto()
    USER_REPORTED = auto()
    
class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4
    )

    telegram_id: Mapped[int] = mapped_column(
        Integer, 
        unique=True,
        index=True,
        nullable=False
    )

    university_id: Mapped[str] = mapped_column(
        String(50),
        index=True
    )

    department_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("departments.department_id"),
        index=True
    )

    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole),
        default=UserRole.USER
    )

    section: Mapped[str | None] = mapped_column(
        String(20),
        index=True
    )

    section_source: Mapped[SectionSource | None] = mapped_column(
        SQLEnum(SectionSource)
    )

    is_credential_valid: Mapped[bool] = mapped_column(default=True)

    last_used: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    department: Mapped["Department"] = relationship(
        back_populates="users"
    )
    credential: Mapped["UserCredential"] = relationship(
        "UserCredential",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan"
    )
    semester_results: Mapped[List["SemesterResult"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan"
    )
    courses: Mapped[List["UserCourse"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan"
    )


class UserCredential(Base):
    __tablename__ = "user_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id",ondelete="CASCADE"),
        primary_key=True
    )

    encrypted_password: Mapped[str] = mapped_column(String(255))
    iv: Mapped[str] = mapped_column(String(255))

    algorithm: Mapped[str] = mapped_column(
        String(50),
        default="AES-256-GCM"
    )

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship("User", back_populates="credential")

class Campus(Base):
    __tablename__ = "campuses"
    
    campus_id: Mapped[str] = mapped_column(
        String(50),
        primary_key=True
    )  # Like CTBE

    full_name: Mapped[str] = mapped_column(String(255))

    departments: Mapped[List["Department"]] = relationship(back_populates="campus")

class Department(Base):
    __tablename__ = "departments"
    
    department_id: Mapped[str] = mapped_column(
        String(50),
        primary_key=True
    )  # Like SITE

    full_name: Mapped[str] = mapped_column(String(255))

    campus_id: Mapped[str] = mapped_column(
        ForeignKey("campuses.campus_id")
    )

    campus: Mapped["Campus"] = relationship(back_populates="departments")
    users: Mapped[List["User"]] = relationship(back_populates="department")
    department_courses: Mapped[List["DepartmentCourse"]] = relationship(
        back_populates="department"
    )

class Course(Base):
    __tablename__ = "courses"

    course_id: Mapped[str] = mapped_column(
        String(50),
        primary_key=True)  # Like SECT-3082
    
    course_name: Mapped[str] = mapped_column(
        String(255), 
        nullable=False
    )

    credit_hours: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    ects: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    user_courses: Mapped[List["UserCourse"]] = relationship(
        back_populates="course"
    )
    department_courses: Mapped[List["DepartmentCourse"]] = relationship(
        back_populates="course"
    )

"""
A department can have multiple courses, and a course can belong to multiple departments.
This is a many-to-many relationship, which is why we have a junction table called department_courses
"""
class DepartmentCourse(Base):
    __tablename__ = "department_courses"

    department_id: Mapped[str] = mapped_column(
        ForeignKey("departments.department_id"),
        primary_key=True
    )

    course_id: Mapped[str] = mapped_column(
        ForeignKey("courses.course_id"),
        primary_key=True
    )

    department: Mapped["Department"] = relationship(
        back_populates="department_courses"
    )

    course: Mapped["Course"] = relationship(
        back_populates="department_courses"
    )

"""
A user can have multiple courses, and a course can belong to multiple users. 
Four attributes are used as primary key because a user can take the same course in different academic years and semesters.
"""
class UserCourse(Base):
    __tablename__ = "user_courses"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )

    course_id: Mapped[str] = mapped_column(
        ForeignKey("courses.course_id")
    )

    academic_year: Mapped[str] = mapped_column(
        String(50), 
        nullable=False
    )  # Like 2023/2024

    semester: Mapped[Semester] = mapped_column(
        SQLEnum(Semester),
        nullable=False
    )

    
    assessment: Mapped["Assessment"] = relationship(
        back_populates="user_course",
        uselist=False,
        cascade="all, delete-orphan"
    )
    user: Mapped["User"] = relationship(back_populates="courses")
    course: Mapped["Course"] = relationship(back_populates="user_courses")

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "course_id",
            "academic_year",
            "semester",
            name="uq_user_course_term"
        ),
    )
    

class Assessment(Base):
    __tablename__="assessments"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4
    )
    user_course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_courses.id", ondelete="CASCADE"),
        unique=True
    )

    encrypted_assessment_detail: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    encrypted_grade: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    iv:Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    user_course: Mapped["UserCourse"] = relationship(
        back_populates="assessment"
    )

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4
    )

    telegram_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True
    )

    action: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    details: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True
    )

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

"""
This is used to store system-wide settings that can be configured by the admin. 
Such as - is_scheduling_enabled, is_maintenance_mode, etc.
"""
class SystemSetting(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(
        String(255),
        primary_key=True
    )

    value: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )


class SemesterResult(Base):
    __tablename__ = "semester_results"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id",ondelete="CASCADE"),
        nullable=False
    )

    academic_year: Mapped[str] = mapped_column(
        String(50), 
        nullable=False
    )

    semester: Mapped[Semester] = mapped_column(
        SQLEnum(Semester),
        nullable=False
    )

    encrypted_result_detail: Mapped[str] = mapped_column(
        Text, 
        nullable=False
    )

    iv: Mapped[str] = mapped_column(String(255), nullable=False)

    user: Mapped["User"] = relationship(
        back_populates="semester_results"
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "academic_year",
            "semester",
            name="uq_user_semester_result"
        ),
    )

class CronRun(Base):
    __tablename__ = "cron_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    status: Mapped[CronRunStatus] = mapped_column(
        SQLEnum(CronRunStatus),
        default=CronRunStatus.RUNNING
    )

    trigger: Mapped[str] = mapped_column(
        String(30),
        default="scheduled"
    )

    scans: Mapped[list["CohortScan"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan"
    )

class CohortState(Base):
    __tablename__ = "cohort_states"

    department_id: Mapped[str] = mapped_column(
        ForeignKey("departments.department_id"),
        primary_key=True
    )

    academic_year: Mapped[str] = mapped_column(
        String(20),
        primary_key=True
    )

    semester: Mapped[Semester] = mapped_column(
        SQLEnum(Semester),
        primary_key=True
    )

    section: Mapped[str] = mapped_column(
        String(20),
        primary_key=True
    )

    representative_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    last_probe_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    last_grade_change_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    last_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cron_runs.id")
    )

    status: Mapped[CohortScanStatus] = mapped_column(
        SQLEnum(CohortScanStatus),
        default=CohortScanStatus.COMPLETED
    )

    resume_after_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    users_checked: Mapped[int] = mapped_column(
        default=0
    )

    total_users: Mapped[int] = mapped_column(
        default=0
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    department = relationship("Department")

    representative = relationship(
        "User",
        foreign_keys=[representative_user_id]
    )

    resume_after_user = relationship(
        "User",
        foreign_keys=[resume_after_user_id]
    )

    last_run = relationship("CronRun")

class CohortScan(Base):
    __tablename__ = "cohort_scans"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cron_runs.id")
    )

    department_id: Mapped[str] = mapped_column(
        ForeignKey("departments.department_id")
    )

    academic_year: Mapped[str] = mapped_column(
        String(20)
    )

    semester: Mapped[Semester] = mapped_column(
        SQLEnum(Semester)
    )

    section: Mapped[str] = mapped_column(
        String(20),
        nullable=False
    )
 
    representative_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    status: Mapped[CohortScanStatus] = mapped_column(
        SQLEnum(CohortScanStatus)
    )

    grade_change: Mapped[GradeChangeStatus] = mapped_column(
        SQLEnum(GradeChangeStatus)
    )

    users_checked: Mapped[int] = mapped_column(default=0)

    total_users: Mapped[int] = mapped_column(default=0)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    run = relationship(
        "CronRun",
        back_populates="scans"
    )

    department = relationship("Department")

    representative = relationship("User")

    __table_args__ = (
        UniqueConstraint(
            "run_id", 
            "department_id", 
            "academic_year", 
            "semester", 
            "section",
            name="uq_scan_per_run_cohort_section"
        ),
        Index(
            "ix_cohort_scans_cohort", 
            "department_id", 
            "academic_year", 
            "semester",
            "section"
        ),
    )