import uuid
from enum import Enum
from typing import List, Optional
from datetime import datetime

from sqlalchemy import JSON, Integer, String, ForeignKey, Text, DateTime, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column, UniqueConstraint

class UserRole(Enum):
    USER="user"
    ADMIN="admin"

class Semester(Enum):
    FIRST="first"
    SECOND="second"
    THIRD="third"
  
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
        ForeignKey("departments.department_id")
    )

    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole),
        default=UserRole.USER
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
        uselist=False
    )
    semester_results: Mapped[List["SemesterResult"]] = relationship(
        back_populates="user"
    )
    courses: Mapped[List["UserCourse"]] = relationship(
        back_populates="user"
    )


class UserCredential(Base):
    __tablename__ = "user_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"),
        primary_key=True
    )

    encrypted_password: Mapped[str] = mapped_column(String(255))
    iv: Mapped[str] = mapped_column(String(255))

    algorithm: Mapped[str] = mapped_column(
        String(50),
        default="AES-256-CBC"
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
        ForeignKey("users.id")
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
        ForeignKey("user_courses.id"),
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

    user: Mapped["UserCourse"] = relationship(
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
This is used to store system-wide settings that can be configured by the admin. Such as - is_scheduling_enabled, is_maintenance_mode, etc.
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
        ForeignKey("users.id"),
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