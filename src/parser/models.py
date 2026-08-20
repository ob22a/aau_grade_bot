"""Immutable parser outputs shared by the AAU adapter and application services."""

from __future__ import annotations
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ParserWarningCode(StrEnum):
    MISSING_OPTIONAL_PROFILE_FIELD = "missing_optional_profile_field"
    UNKNOWN_NONCRITICAL_VALUE = "unknown_noncritical_value"


class ParserWarning(BaseModel):
    """Recoverable parser observation safe to log and present to administrators."""

    model_config = ConfigDict(frozen=True)

    code: ParserWarningCode
    page_kind: str
    detail: str


class ParsedPortalResult(BaseModel):
    """Base for stable parser DTOs; warnings never imply grade uncertainty."""

    model_config = ConfigDict(frozen=True)

    warnings: tuple[ParserWarning, ...] = Field(default_factory=tuple)


class AssessmentReference(BaseModel):
    """Opaque identifiers required to fetch assessment details safely."""

    academic_year_id: str
    semester_id: str
    course_id: str


class CourseGrade(BaseModel):
    course_number: int
    course_name: str
    course_code: str
    credit_hours: float
    ects: float
    grade: str
    assessment: AssessmentReference


class GradeReportSummary(BaseModel):
    sgp: float
    sgpa: float
    cgp: float
    cgpa: float
    academic_status: str


class GradeReport(ParsedPortalResult):
    academic_year: str
    year_label: str
    semester_label: str
    course_grades: tuple[CourseGrade, ...]
    summary: GradeReportSummary


class StudentProfileData(BaseModel):
    """Student profile information from home page."""

    model_config = ConfigDict(frozen=True)

    full_name: str
    student_id: str
    department: str | None = None
    year_level: str  # e.g., "Year III"
    campus: str | None = None  # May not be visible in profile
    section: str | None = None  # May not be visible in profile


class ProfilePageResult(ParsedPortalResult):
    """Parsed home page containing student profile information."""

    profile: StudentProfileData


class AssessmentScore(BaseModel):
    """Individual assessment score component."""

    model_config = ConfigDict(frozen=True)

    sequence: int  # 1, 2, 3, etc.
    name: str  # e.g., "Final Exam (50%)"
    score: float  # e.g., 50


class AssessmentDetails(BaseModel):
    """Complete assessment details for a single course."""

    model_config = ConfigDict(frozen=True)

    course_name: str
    scores: tuple[AssessmentScore, ...]
    total_mark: float
    total_possible: float


class AssessmentDetailsResult(ParsedPortalResult):
    """Parsed assessment modal containing breakdown of course assessment."""

    assessment: AssessmentDetails

