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
        university_id = normalize_aau_undergraduate_id(request.university_id)

        if self.cache is not None:
            cache_key = f"registration:{request.telegram_id}"
            if await self.cache.get(cache_key):
                raise RuntimeError("Registration is rate-limited for this user")

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
                from database.models import User, UserCredential, AuditLog

                async with SqlAlchemyRepositoryUnitOfWork(self.session_factory) as uow:
                    db_user = await uow.users.get_by_telegram_id(request.telegram_id)
                    if db_user is None:
                        db_user = User(
                            telegram_id=request.telegram_id,
                            university_id=university_id,
                            department_id=profile.profile.department if profile and profile.profile and profile.profile.department else None,
                        )
                        uow.session.add(db_user)
                        await uow.session.flush()
                    else:
                        db_user.university_id = university_id

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
                    
                    # Persist Grade Reports to DB
                    if _grade_report:
                        from database.models import SemesterResult, Semester
                        
                        def parse_semester(label: str) -> Semester:
                            lab = label.lower()
                            if "2" in lab or "two" in lab or "second" in lab or " ii" in lab:
                                return Semester.SECOND
                            if "3" in lab or "three" in lab or "third" in lab or "iii" in lab:
                                return Semester.THIRD
                            return Semester.FIRST

                        # Clear old grades to avoid duplicates/conflicts on re-registration
                        from sqlalchemy import delete
                        await uow.session.execute(delete(SemesterResult).where(SemesterResult.user_id == db_user.id))

                        for rep in _grade_report:
                            # Serialize GradeReport to JSON
                            rep_dict = rep.model_dump()
                            # Convert tuples to lists for JSON serialization if necessary, though model_dump handles it
                            rep_json = json.dumps(rep_dict)
                            enc_rep = self.cipher.encrypt(rep_json)
                            rep_payload = Ciphertext.from_token(enc_rep)
                            rep_iv = base64.urlsafe_b64encode(rep_payload.nonce).decode("ascii")

                            sr = SemesterResult(
                                user_id=db_user.id,
                                academic_year=rep.academic_year,
                                semester=parse_semester(rep.semester_label),
                                encrypted_result_detail=enc_rep,
                                iv=rep_iv,
                            )
                            uow.session.add(sr)

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
