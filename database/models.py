from datetime import datetime
from typing import List, Optional
from sqlalchemy import String, DateTime, ForeignKey, JSON, Integer, BigInteger, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import uuid

class Base(DeclarativeBase):
    pass

class Campus(Base):
    __tablename__ = "campuses"
    
    campus_id: Mapped[str] = mapped_column(String(50), primary_key=True)  # e.g., "CTBE"
    full_name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    departments: Mapped[List["Department"]] = relationship(back_populates="campus")

class Department(Base):
    __tablename__ = "departments"
    
    department_id: Mapped[str] = mapped_column(String(50), primary_key=True)  # e.g., "SITE"
    full_name: Mapped[str] = mapped_column(String(255))
    campus_id: Mapped[str] = mapped_column(ForeignKey("campuses.campus_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    campus: Mapped["Campus"] = relationship(back_populates="departments")
    users: Mapped[List["User"]] = relationship(back_populates="department")

class User(Base):
    __tablename__ = "users"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    telegram_username: Mapped[Optional[str]] = mapped_column(String(255))
    university_id: Mapped[str] = mapped_column(String(50), index=True) # Portal ID
    campus_id: Mapped[Optional[str]] = mapped_column(ForeignKey("campuses.campus_id"))
    department_id: Mapped[Optional[str]] = mapped_column(ForeignKey("departments.department_id"))
    
    academic_year: Mapped[Optional[str]] = mapped_column(String(50))  # e.g., "Year 2"
    semester: Mapped[Optional[str]] = mapped_column(String(50))       # e.g., "Semester 1"
    
    role: Mapped[str] = mapped_column(String(50), default="user")
    is_credential_valid: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    department: Mapped[Optional["Department"]] = relationship(back_populates="users")
    credential: Mapped["UserCredential"] = relationship(back_populates="user", uselist=False)

class UserCredential(Base):
    __tablename__ = "user_credentials"
    
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    encrypted_password: Mapped[str] = mapped_column(Text)
    iv: Mapped[str] = mapped_column(String(255))
    algorithm: Mapped[str] = mapped_column(String(50), default="AES-256-CBC")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="credential")

class Course(Base):
    __tablename__ = "courses"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    course_id: Mapped[str] = mapped_column(String(50), index=True) # e.g., "ELEC101"
    course_name: Mapped[str] = mapped_column(String(255))
    campus_id: Mapped[str] = mapped_column(String(50), index=True)
    department_id: Mapped[str] = mapped_column(String(50), index=True)
    academic_year: Mapped[str] = mapped_column(String(50))
    semester: Mapped[str] = mapped_column(String(50))
    
    # Ensure we don't duplicate courses for the same campus/dept/year/sem
    from sqlalchemy import UniqueConstraint
    __table_args__ = (UniqueConstraint('course_id', 'campus_id', 'department_id', 'academic_year', 'semester', name='_course_uc'),)

class Assessment(Base):
    __tablename__ = "assessments"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    
    campus_id: Mapped[str] = mapped_column(String(50))
    department_id: Mapped[str] = mapped_column(String(50))
    course_id: Mapped[str] = mapped_column(String(50))
    
    academic_year: Mapped[str] = mapped_column(String(50))
    semester: Mapped[str] = mapped_column(String(50))
    year_level: Mapped[Optional[str]] = mapped_column(String(50))  # "Year III"
    year_number: Mapped[Optional[int]] = mapped_column()  # 3
    
    assessment_data: Mapped[Optional[dict]] = mapped_column(JSON) # Store raw JSON if not encrypted
    encrypted_data: Mapped[Optional[str]] = mapped_column(Text) # Store encrypted Base64
    iv: Mapped[Optional[str]] = mapped_column(String(255))
    last_updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger, index=True)
    action: Mapped[str] = mapped_column(String(100))
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    source: Mapped[str] = mapped_column(String(100), default="telegram_bot")

class Grade(Base):
    __tablename__ = "grades"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    
    campus_id: Mapped[str] = mapped_column(String(50))
    department_id: Mapped[str] = mapped_column(String(50))
    course_id: Mapped[str] = mapped_column(String(50)) # Course Code
    course_name: Mapped[Optional[str]] = mapped_column(String(255))  # Store course name
    
    academic_year: Mapped[str] = mapped_column(String(50))
    semester: Mapped[str] = mapped_column(String(50))
    year_level: Mapped[Optional[str]] = mapped_column(String(50))  # "Year III"
    year_number: Mapped[Optional[int]] = mapped_column()  # 3
    
    grade: Mapped[str] = mapped_column(String(255)) # Scrambled encrypted string
    credit_hour: Mapped[Optional[str]] = mapped_column(String(255))
    ects: Mapped[Optional[str]] = mapped_column(String(255))
    iv: Mapped[Optional[str]] = mapped_column(String(255))
    last_updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class GradeCheckStatus(Base):
    __tablename__ = "grade_check_status"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    campus_id: Mapped[str] = mapped_column(String(50))
    department_id: Mapped[str] = mapped_column(String(50))
    academic_year: Mapped[str] = mapped_column(String(50))
    semester: Mapped[str] = mapped_column(String(50))
    
    last_checked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_full_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

class SystemSetting(Base):
    __tablename__ = "system_settings"
    
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class SemesterResult(Base):
    __tablename__ = "semester_results"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    
    academic_year: Mapped[str] = mapped_column(String(100))
    semester: Mapped[str] = mapped_column(String(50))
    year_level: Mapped[Optional[str]] = mapped_column(String(50))  # "Year III"
    year_number: Mapped[Optional[int]] = mapped_column()  # 3
    
    sgpa: Mapped[str] = mapped_column(String(255))
    cgpa: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(255))
    iv: Mapped[Optional[str]] = mapped_column(String(255))
    
    last_updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
