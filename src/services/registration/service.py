"""Registration workflow service."""

from __future__ import annotations

import json
import base64
from dataclasses import dataclass
from typing import Protocol, Any

from clients.aau_portal import PortalAuthenticationError
from crypto.cipher import AesGcmCipher, Ciphertext
from dto.bot import RegistrationRequest, RegistrationResult
from utils.validation import normalize_aau_undergraduate_id
from parser.models import ProfilePageResult, GradeReport


class UserWriter(Protocol):
    async def add(self, user: Any) -> None: ...


class CredentialWriter(Protocol):
    async def add(self, credential: Any) -> None: ...


class AuditWriter(Protocol):
    async def add(self, audit_log: Any) -> None: ...


@dataclass(frozen=True)
class RegistrationOutcome:
    """Result of a registration attempt."""
    profile: ProfilePageResult
    result: RegistrationResult


class RegistrationService:
    """Register a student after validating AAU credentials once."""

    def __init__(
        self,
        portal_client: Any,
        cipher: AesGcmCipher,
        user_repository: UserWriter | None = None,
        credential_repository: CredentialWriter | None = None,
        audit_repository: AuditWriter | None = None,
        cache: Any | None = None,
        session_factory: Any | None = None,
    ) -> None:
        self.portal_client = portal_client
        self.cipher = cipher
        self.user_repository = user_repository
        self.credential_repository = credential_repository
        self.audit_repository = audit_repository
        self.cache = cache
        self.session_factory = session_factory

    async def register(self, request: RegistrationRequest) -> RegistrationOutcome:
        """
        Coordinates user registration.
        Validates credentials via portal scrape, writes user details, and logs the audit event.
        """
        university_id = normalize_aau_undergraduate_id(request.university_id)

        if self.cache is not None:
            cache_key = f"registration:{request.telegram_id}"
            if await self.cache.get(cache_key):
                raise RuntimeError("Registration is rate-limited for this user")
            
            lock_key = f"lock:reg:{request.telegram_id}"
            if not await self.cache.acquire_lock(lock_key, ttl_seconds=60):
                raise RuntimeError("Registration is already in progress.")

        try:
            try:
                profile, _grade_report = await self.portal_client.scrape(
                    university_id,
                    request.password,
                    university_id,
                )
            except PortalAuthenticationError:
                raise

            encrypted_token = self.cipher.encrypt(request.password)
            payload = Ciphertext.from_token(encrypted_token)
            nonce_token = base64.urlsafe_b64encode(payload.nonce).decode("ascii")

            if self.user_repository is not None:
                await self.user_repository.add(
                    {
                        "telegram_id": request.telegram_id,
                        "university_id": university_id,
                        "department": profile.profile.department or "Unknown",
                        "full_name": profile.profile.full_name,
                    }
                )

            if self.credential_repository is not None:
                await self.credential_repository.add(
                    {
                        "telegram_id": request.telegram_id,
                        "encrypted_password": encrypted_token,
                        "iv": nonce_token,
                        "algorithm": "AES-256-GCM",
                    }
                )

            if self.audit_repository is not None:
                await self.audit_repository.add(
                    {
                        "telegram_id": request.telegram_id,
                        "action": "register",
                        "details": {"university_id": university_id},
                    }
                )

            if self.session_factory is not None:
                try:
                    from repositories.sqlalchemy.unit_of_work import SqlAlchemyRepositoryUnitOfWork
                    from database.models import User, UserCredential, AuditLog, SectionSource, Department, Course, UserCourse, Assessment

                    async with SqlAlchemyRepositoryUnitOfWork(self.session_factory) as uow:
                        db_user = await uow.users.get_by_telegram_id(request.telegram_id)
                    
                        # Resolve department
                        dept_id = None
                        if profile and profile.profile and profile.profile.department:
                            from sqlalchemy import select
                            dept_name = profile.profile.department
                            stmt = select(Department).where(Department.full_name == dept_name)
                            if request.campus:
                                stmt = stmt.where(Department.campus_id == request.campus)
                            dept = await uow.session.scalar(stmt)
                            if dept:
                                dept_id = dept.department_id

                        if db_user is None:
                            db_user = User(
                                telegram_id=request.telegram_id,
                                university_id=university_id,
                                department_id=dept_id,
                            )
                            uow.session.add(db_user)
                            await uow.session.flush()
                        else:
                            db_user.university_id = university_id
                            if dept_id:
                                db_user.department_id = dept_id

                        # Handle Section
                        if request.section:
                            db_user.section = request.section
                            db_user.section_source = SectionSource.USER_REPORTED
                        elif profile and profile.profile and profile.profile.section:
                            db_user.section = profile.profile.section
                            db_user.section_source = SectionSource.SCRAPED

                        cred = await uow.credentials.get_by_user_id(db_user.id)
                        if cred is None:
                            cred = UserCredential(
                                user_id=db_user.id,
                                encrypted_password=encrypted_token,
                                iv=nonce_token,
                                algorithm="AES-256-GCM",
                            )
                            uow.session.add(cred)
                        else:
                            cred.encrypted_password = encrypted_token
                            cred.iv = nonce_token

                        audit = AuditLog(
                            telegram_id=request.telegram_id,
                            action="register",
                            details={"university_id": university_id},
                        )
                        uow.session.add(audit)
                    
                        # Persist Grade Reports and Assessments to DB
                        if _grade_report:
                            from database.models import SemesterResult, Semester
                            from sqlalchemy import delete, select
                        
                            def parse_semester(label: str) -> Semester:
                                lab = label.lower()
                                if "2" in lab or "two" in lab or "second" in lab or " ii" in lab:
                                    return Semester.SECOND
                                if "3" in lab or "three" in lab or "third" in lab or "iii" in lab:
                                    return Semester.THIRD
                                return Semester.FIRST

                            # Clear old grades to avoid duplicates/conflicts on re-registration
                            await uow.session.execute(delete(SemesterResult).where(SemesterResult.user_id == db_user.id))

                            for rep in _grade_report:
                                sem = parse_semester(rep.semester)
                            
                                # Serialize GradeReport to JSON
                                rep_dict = rep.model_dump()
                                rep_json = json.dumps(rep_dict)
                                enc_rep = self.cipher.encrypt(rep_json)
                                rep_payload = Ciphertext.from_token(enc_rep)
                                rep_iv = base64.urlsafe_b64encode(rep_payload.nonce).decode("ascii")

                                sr = SemesterResult(
                                    user_id=db_user.id,
                                    academic_year=rep.academic_year,
                                    semester=sem,
                                    encrypted_result_detail=enc_rep,
                                    iv=rep_iv,
                                )
                                uow.session.add(sr)
                            
                                # Save Courses, UserCourses, and Assessments
                                for cg in rep.course_grades:
                                    # Ensure Course exists
                                    course_db = await uow.session.scalar(select(Course).where(Course.course_id == cg.course_code))
                                    if not course_db:
                                        course_db = Course(
                                            course_id=cg.course_code,
                                            course_name=cg.course_name,
                                            credit_hours=int(cg.credit_hours) if cg.credit_hours else 0,
                                            ects=int(cg.ects) if cg.ects else 0,
                                        )
                                        uow.session.add(course_db)
                                        await uow.session.flush()

                                    # Create or update UserCourse
                                    uc_stmt = select(UserCourse).where(
                                        UserCourse.user_id == db_user.id,
                                        UserCourse.course_id == course_db.course_id,
                                        UserCourse.academic_year == rep.academic_year,
                                        UserCourse.semester == sem
                                    )
                                    uc_db = await uow.session.scalar(uc_stmt)
                                    if not uc_db:
                                        uc_db = UserCourse(
                                            user_id=db_user.id,
                                            course_id=course_db.course_id,
                                            academic_year=rep.academic_year,
                                            semester=sem
                                        )
                                        uow.session.add(uc_db)
                                        await uow.session.flush()

                                    # Save Assessment reference
                                    asm_dict = {
                                        "reference": cg.assessment.model_dump() if cg.assessment else None,
                                        "grade": cg.grade
                                    }
                                    enc_asm = self.cipher.encrypt(json.dumps(asm_dict))
                                    asm_payload = Ciphertext.from_token(enc_asm)
                                    asm_iv = base64.urlsafe_b64encode(asm_payload.nonce).decode("ascii")

                                    asm_stmt = select(Assessment).where(Assessment.user_course_id == uc_db.id)
                                    asm_db = await uow.session.scalar(asm_stmt)
                                    if not asm_db:
                                        asm_db = Assessment(
                                            user_course_id=uc_db.id,
                                            encrypted_assessment_detail=enc_asm,
                                            encrypted_grade=enc_asm,
                                            iv=asm_iv
                                        )
                                        uow.session.add(asm_db)
                                    else:
                                        asm_db.encrypted_assessment_detail = enc_asm
                                        asm_db.encrypted_grade = enc_asm
                                        asm_db.iv = asm_iv

                        await uow.commit()
                except Exception as db_exc:
                    import logging
                    logging.getLogger(__name__).warning(f"Registration DB persistence warning: {db_exc}")

            if self.cache is not None:
                await self.cache.set(f"registration:{request.telegram_id}", "1", ttl_seconds=300)

            # Format auto-display message
            grade_message = ""
            if _grade_report:
                from services.grades.service import format_grade_report_page
                # Auto-display the first (most recent) term
                rep = _grade_report[0]
            
                course_dicts = []
                for cg in rep.course_grades:
                    course_dicts.append({
                        "course_code": cg.course_code,
                        "course_name": cg.course_name,
                        "credit_hours": cg.credit_hours,
                        "ects": cg.ects,
                        "grade": cg.grade,
                    })
            
                summary_dict = None
                if rep.summary:
                    summary_dict = {
                        "sgp": rep.summary.sgp,
                        "sgpa": rep.summary.sgpa,
                        "cgpa": rep.summary.cgpa,
                        "academic_status": rep.summary.academic_status,
                    }
                
                formatted = format_grade_report_page(
                academic_year=rep.academic_year,
                semester_label=rep.semester_label,
                year_label=rep.year_label,
                course_grades=course_dicts,
                summary=summary_dict,
            )
            grade_message = f"\n\n{formatted}"

            return RegistrationOutcome(
                profile=profile,
                result=RegistrationResult(
                    success=True, 
                    message=f"✅ <b>Registration complete!</b>\n\n"
                            f"University ID: <code>{university_id}</code>\n"
                            f"Department: <code>{profile.profile.department or 'Unknown'}</code>"
                            f"{grade_message}"
                ),
            )
        finally:
            if self.cache is not None:
                await self.cache.release_lock(f"lock:reg:{request.telegram_id}")
