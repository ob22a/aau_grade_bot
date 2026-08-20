"""Account inactivity and deletion workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dto.bot import AccountDeletionRequest


@dataclass(frozen=True)
class AccountLifecycleResult:
    """Result of an account lifecycle action."""
    message: str
    deleted: bool = False


class AccountLifecycleService:
    """Handle inactivity notices, self-deletion, and audit cleanup.

    The implementation stays small for Phase 6 and exposes the hooks needed by the
    handler layer and future background jobs.
    """

    def __init__(self, user_repository: Any | None = None, audit_repository: Any | None = None, notifier: Any | None = None, session_factory: Any | None = None, portal_client: Any | None = None) -> None:
        self.user_repository = user_repository
        self.audit_repository = audit_repository
        self.notifier = notifier
        self.session_factory = session_factory
        self.portal_client = portal_client

    async def is_registered(self, telegram_id: int) -> bool:
        """Returns True if the user exists in the database."""
        if self.session_factory is not None:
            from repositories.sqlalchemy.unit_of_work import SqlAlchemyRepositoryUnitOfWork
            async with SqlAlchemyRepositoryUnitOfWork(self.session_factory) as uow:
                user = await uow.users.get_by_telegram_id(telegram_id)
                return user is not None
        return False

    async def request_deletion(self, request: AccountDeletionRequest) -> AccountLifecycleResult:
        """
        Securely deletes a user's account and scrambles their data.
        Ensures irreversible removal of credentials and grades.
        """
        if not request.confirm:
            return AccountLifecycleResult(message="Confirmation required before deletion")
            
        if self.session_factory is not None:
            import random
            from repositories.sqlalchemy.unit_of_work import SqlAlchemyRepositoryUnitOfWork
            from database.models import AuditLog
            
            async with SqlAlchemyRepositoryUnitOfWork(self.session_factory) as uow:
                user = await uow.users.get_by_telegram_id(request.telegram_id)
                if user is not None:
                    from sqlalchemy import select
                    from database.models import UserCredential, SemesterResult, UserCourse, Assessment
                    
                    # 1. Scramble related credentials and grades to prevent recovery
                    cred = await uow.credentials.get_by_user_id(user.id)
                    if cred:
                        cred.encrypted_password = "deleted_password"
                        cred.iv = "deleted_iv"
                        
                    results = await uow.semester_results.get_by_user_id(user.id)
                    for res in results:
                        res.encrypted_result_detail = "deleted_result"
                        res.iv = "deleted_iv"
                        
                    courses = await uow.user_courses.get_by_user_id(user.id)
                    for c in courses:
                        assessment = await uow.assessments.get_by_user_course_id(c.id)
                        if assessment:
                            assessment.encrypted_assessment_detail = "deleted_assessment"
                            assessment.encrypted_grade = "deleted_grade"
                            assessment.iv = "deleted_iv"

                    user.telegram_id = -random.randint(1000000, 9999999)
                    user.university_id = "deleted_account"
                    user.department_id = None
                    user.section = "none"
                    await uow.commit() # Flush and commit the dummy data
                    
                    # 2. Actually delete the scrambled row
                    await uow.users.remove(user)
                    
                    # 3. Add audit log
                    audit = AuditLog(
                        telegram_id=request.telegram_id,
                        action="account_deletion_requested",
                        details={"confirmed": True, "reason": request.reason},
                    )
                    await uow.audit_logs.add(audit)
                    await uow.commit()
                    return AccountLifecycleResult(message="Account and all credentials securely deleted.", deleted=True)
                else:
                    return AccountLifecycleResult(message="You are not registered in the system.", deleted=False)
                    
        else:
            if self.user_repository is not None:
                user = None
                if hasattr(self.user_repository, "get_by_telegram_id"):
                    user = await self.user_repository.get_by_telegram_id(request.telegram_id)
                if user is not None and hasattr(self.user_repository, "remove"):
                    await self.user_repository.remove(user)
                    if self.audit_repository is not None:
                        await self.audit_repository.add(
                            {
                                "telegram_id": request.telegram_id,
                                "action": "account_deletion_requested",
                                "details": {"confirmed": True},
                            }
                        )
                    return AccountLifecycleResult(message="Account deletion queued", deleted=True)
                else:
                    return AccountLifecycleResult(message="You are not registered in the system.", deleted=False)

        return AccountLifecycleResult(message="Account deletion not available without database connection.", deleted=False)

    async def update_university_id(self, telegram_id: int, new_id: str) -> bool:
        if self.session_factory is not None:
            from repositories.sqlalchemy.unit_of_work import SqlAlchemyRepositoryUnitOfWork
            async with SqlAlchemyRepositoryUnitOfWork(self.session_factory) as uow:
                user = await uow.users.get_by_telegram_id(telegram_id)
                if user is not None:
                    user.university_id = new_id
                    await uow.commit()
                    return True
        return False

    async def update_department(self, telegram_id: int, new_dept: str) -> bool:
        if self.session_factory is not None:
            from repositories.sqlalchemy.unit_of_work import SqlAlchemyRepositoryUnitOfWork
            from database.models import Department
            async with SqlAlchemyRepositoryUnitOfWork(self.session_factory) as uow:
                user = await uow.users.get_by_telegram_id(telegram_id)
                if user is not None:
                    # Dynamically seed if not exists
                    existing = await uow.departments.get_by_id(new_dept)
                    if not existing:
                        import uuid
                        new_d = Department(
                            department_id=f"{new_dept}_{str(uuid.uuid4())[:4]}",
                            full_name=new_dept,
                            campus_id="Main" # fallback campus
                        )
                        await uow.departments.add(new_d)
                        await uow.session.flush()
                        user.department_id = new_d.department_id
                    else:
                        user.department_id = new_dept
                        
                    await uow.commit()
                    return True
        return False

    async def update_campus(self, telegram_id: int, new_campus: str) -> bool:
        if self.session_factory is not None:
            from repositories.sqlalchemy.unit_of_work import SqlAlchemyRepositoryUnitOfWork
            from sqlalchemy.orm import selectinload
            from sqlalchemy import select
            from database.models import Department, User
            async with SqlAlchemyRepositoryUnitOfWork(self.session_factory) as uow:
                user = await uow.users.get_by_telegram_id(telegram_id)
                if user is not None:
                    if not user.department_id:
                        # Cannot update campus without a department
                        return False
                    
                    user_dept = await uow.departments.get_by_id(user.department_id)
                    dept_name = user_dept.full_name if user_dept else "Unknown"
                    # Find or create a department with this name in the new campus
                    dept = await uow.departments.get_by_name_and_campus(dept_name, new_campus)
                    if not dept:
                        import uuid
                        # Create new department entry for this campus
                        generated_id = "".join([w[0].upper() for w in dept_name.split() if w.isalpha() and len(w) > 2])
                        if len(generated_id) < 2:
                            generated_id = dept_name[:4].upper()
                            
                        existing = await uow.departments.get_by_id(generated_id)
                        if existing:
                            generated_id = f"{generated_id}_{str(uuid.uuid4())[:4]}"
                            
                        dept = Department(
                            department_id=generated_id,
                            full_name=dept_name,
                            campus_id=new_campus
                        )
                        await uow.departments.add(dept)
                        await uow.session.flush()
                        
                    user.department_id = dept.department_id
                    await uow.commit()
                    return True
        return False

    async def update_section(self, telegram_id: int, new_section: str) -> bool:
        """Update the user's section."""
        if self.session_factory is not None:
            from repositories.sqlalchemy.unit_of_work import SqlAlchemyRepositoryUnitOfWork
            from database.models import SectionSource
            async with SqlAlchemyRepositoryUnitOfWork(self.session_factory) as uow:
                user = await uow.users.get_by_telegram_id(telegram_id)
                if user is not None:
                    user.section = new_section
                    user.section_source = SectionSource.USER_REPORTED
                    await uow.commit()
                    return True
        return False

    async def update_password(self, telegram_id: int, new_password: str, cipher: Any) -> tuple[bool, str]:
        if self.session_factory is not None:
            from repositories.sqlalchemy.unit_of_work import SqlAlchemyRepositoryUnitOfWork
            from database.models import UserCredential
            from sqlalchemy import select
            from datetime import datetime, timezone, timedelta
            from clients.aau_portal import PortalAuthenticationError
            
            async with SqlAlchemyRepositoryUnitOfWork(self.session_factory) as uow:
                user = await uow.users.get_by_telegram_id(telegram_id)
                if user is not None:
                    cred = await uow.credentials.get_by_user_id(user.id)
                    if cred:
                        now = datetime.now(timezone.utc)
                        # 1. Check if locked out
                        if cred.locked_until and cred.locked_until > now:
                            return False, f"Too many failed attempts. Password changes are locked until {cred.locked_until.strftime('%Y-%m-%d %H:%M:%S UTC')}."
                            
                        # 2. Verify against AAU portal
                        if self.portal_client:
                            try:
                                # Lightweight verification by fetching profile
                                await self.portal_client.scrape(user.university_id, new_password)
                            except PortalAuthenticationError:
                                cred.failed_attempts = (cred.failed_attempts or 0) + 1
                                if cred.failed_attempts >= 3:
                                    cred.locked_until = now + timedelta(days=3)
                                    await uow.commit()
                                    return False, "Too many failed attempts. To protect your AAU account from being locked by the university, password changes are temporarily disabled for 3 days."
                                else:
                                    await uow.commit()
                                    return False, f"The password you entered is incorrect. Please try again. ({cred.failed_attempts}/3)"
                            except Exception as e:
                                import logging
                                logging.getLogger(__name__).warning(f"Portal verify failed (non-auth error): {e}")
                                return False, "Portal is currently unavailable to verify your new password. Please try again later."
                        
                        # 3. Save new password
                        import base64
                        from crypto.cipher import Ciphertext
                        encrypted_token = cipher.encrypt(new_password)
                        payload = Ciphertext.from_token(encrypted_token)
                        cred.encrypted_password = encrypted_token
                        cred.iv = base64.urlsafe_b64encode(payload.nonce).decode("ascii")
                        cred.is_valid = True
                        cred.failed_attempts = 0
                        cred.locked_until = None
                        await uow.commit()
                        return True, "✅ Password successfully updated and encrypted."
        return False, "Failed to update password. You may need to /register first."

    async def get_decrypted_password(self, telegram_id: int, cipher: Any) -> str | None:
        if self.session_factory is not None:
            from repositories.sqlalchemy.unit_of_work import SqlAlchemyRepositoryUnitOfWork
            from database.models import UserCredential
            from sqlalchemy import select
            async with SqlAlchemyRepositoryUnitOfWork(self.session_factory) as uow:
                user = await uow.users.get_by_telegram_id(telegram_id)
                if user is not None:
                    cred = await uow.credentials.get_by_user_id(user.id)
                    if cred and cred.encrypted_password:
                        try:
                            return cipher.decrypt(cred.encrypted_password)
                        except Exception as e:
                            import logging
                            logging.getLogger(__name__).error(f"Failed to decrypt password for user {telegram_id}: {e}")
                            return None
        return None

    async def get_user_profile(self, telegram_id: int) -> Any | None:
        if self.session_factory is not None:
            from repositories.sqlalchemy.unit_of_work import SqlAlchemyRepositoryUnitOfWork
            from dto.bot import UserProfileDTO
            async with SqlAlchemyRepositoryUnitOfWork(self.session_factory) as uow:
                user = await uow.users.get_by_telegram_id(telegram_id)
                if user is not None:
                    campus_name = "Unknown"
                    if user.department_id:
                        dept = await uow.departments.get_by_id(user.department_id)
                        if dept:
                            campus_name = dept.campus_id
                    return UserProfileDTO(
                        telegram_id=user.telegram_id,
                        university_id=user.university_id,
                        department_id=user.department_id,
                        section=user.section,
                        campus=campus_name
                    )
        return None

    async def cleanup_inactive_users(self, inactivity_days: int) -> int:
        """Find and remove users who haven't used the bot for `inactivity_days`."""
        if self.session_factory is None:
            return 0
            
        from repositories.sqlalchemy.unit_of_work import SqlAlchemyRepositoryUnitOfWork
        from database.models import User
        from sqlalchemy import select
        from datetime import datetime, timedelta, timezone
        from dto.bot import AccountDeletionRequest
        import logging
        
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=inactivity_days)
        deleted_count = 0
        
        async with SqlAlchemyRepositoryUnitOfWork(self.session_factory) as uow:
            inactive_users = await uow.users.get_inactive_users(cutoff_date)
            users_to_delete = inactive_users
            
        for user in users_to_delete:
            req = AccountDeletionRequest(telegram_id=user.telegram_id, confirm=True, reason="inactivity_purge")
            res = await self.request_deletion(req)
            if res.deleted:
                deleted_count += 1
                if self.notifier is not None:
                    try:
                        await self.notifier.send_message(
                            user.telegram_id, 
                            "⚠️ <b>Account Removed</b>\n\nYour account has been automatically removed due to prolonged inactivity to protect your data. To use the bot again, please register."
                        )
                    except Exception as e:
                        logging.getLogger(__name__).warning(f"Could not notify inactive user {user.telegram_id}: {e}")
                        
        if deleted_count > 0 and self.notifier is not None:
            await self.notifier.send_admin_alert(f"🧹 <b>Inactivity Cleanup</b>\nRemoved {deleted_count} inactive users (> {inactivity_days} days).")
            
        return deleted_count

    async def bump_last_used(self, telegram_id: int) -> None:
        """Update the last_used timestamp for the given user."""
        if self.session_factory is not None:
            from repositories.sqlalchemy.unit_of_work import SqlAlchemyRepositoryUnitOfWork
            from sqlalchemy import func
            async with SqlAlchemyRepositoryUnitOfWork(self.session_factory) as uow:
                user = await uow.users.get_by_telegram_id(telegram_id)
                if user is not None:
                    user.last_used = func.now()
                    await uow.commit()
