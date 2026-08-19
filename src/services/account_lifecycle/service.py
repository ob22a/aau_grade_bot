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

    def __init__(self, user_repository: Any | None = None, audit_repository: Any | None = None, notifier: Any | None = None, session_factory: Any | None = None) -> None:
        self.user_repository = user_repository
        self.audit_repository = audit_repository
        self.notifier = notifier
        self.session_factory = session_factory

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
                    cred = await uow.session.scalar(select(UserCredential).where(UserCredential.user_id == user.id))
                    if cred:
                        cred.encrypted_password = "deleted_password"
                        cred.iv = "deleted_iv"
                        
                    results = await uow.session.scalars(select(SemesterResult).where(SemesterResult.user_id == user.id))
                    for res in results.all():
                        res.encrypted_result_detail = "deleted_result"
                        res.iv = "deleted_iv"
                        
                    courses = await uow.session.scalars(select(UserCourse).where(UserCourse.user_id == user.id))
                    for c in courses.all():
                        assessment = await uow.session.scalar(select(Assessment).where(Assessment.user_course_id == c.id))
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
                        details={"confirmed": True},
                    )
                    uow.session.add(audit)
                    await uow.commit()
                    return AccountLifecycleResult(message="Account and all credentials securely deleted.", deleted=True)
                    
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
            async with SqlAlchemyRepositoryUnitOfWork(self.session_factory) as uow:
                user = await uow.users.get_by_telegram_id(telegram_id)
                if user is not None:
                    user.department_id = new_dept
                    await uow.commit()
                    return True
        return False

    async def update_password(self, telegram_id: int, new_password: str, cipher: Any) -> bool:
        if self.session_factory is not None:
            from repositories.sqlalchemy.unit_of_work import SqlAlchemyRepositoryUnitOfWork
            from database.models import UserCredential
            from sqlalchemy import select
            async with SqlAlchemyRepositoryUnitOfWork(self.session_factory) as uow:
                user = await uow.users.get_by_telegram_id(telegram_id)
                if user is not None:
                    cred = await uow.session.scalar(select(UserCredential).where(UserCredential.user_id == user.id))
                    if cred:
                        import base64
                        from crypto.cipher import Ciphertext
                        encrypted_token = cipher.encrypt(new_password)
                        payload = Ciphertext.from_token(encrypted_token)
                        cred.encrypted_password = encrypted_token
                        cred.iv = base64.urlsafe_b64encode(payload.nonce).decode("ascii")
                        await uow.commit()
                        return True
        return False

    async def get_decrypted_password(self, telegram_id: int, cipher: Any) -> str | None:
        if self.session_factory is not None:
            from repositories.sqlalchemy.unit_of_work import SqlAlchemyRepositoryUnitOfWork
            from database.models import UserCredential
            from sqlalchemy import select
            async with SqlAlchemyRepositoryUnitOfWork(self.session_factory) as uow:
                user = await uow.users.get_by_telegram_id(telegram_id)
                if user is not None:
                    cred = await uow.session.scalar(select(UserCredential).where(UserCredential.user_id == user.id))
                    if cred and cred.encrypted_password:
                        return cipher.decrypt(cred.encrypted_password)
        return None

    async def get_user_profile(self, telegram_id: int) -> Any | None:
        if self.session_factory is not None:
            from repositories.sqlalchemy.unit_of_work import SqlAlchemyRepositoryUnitOfWork
            from dto.bot import UserProfileDTO
            async with SqlAlchemyRepositoryUnitOfWork(self.session_factory) as uow:
                user = await uow.users.get_by_telegram_id(telegram_id)
                if user is not None:
                    return UserProfileDTO(
                        telegram_id=user.telegram_id,
                        university_id=user.university_id,
                        department_id=user.department_id,
                        section=user.section
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
            stmt = select(User).where(User.last_used < cutoff_date)
            inactive_users = await uow.session.scalars(stmt)
            users_to_delete = inactive_users.all()
            
        for user in users_to_delete:
            req = AccountDeletionRequest(telegram_id=user.telegram_id, confirm=True)
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
