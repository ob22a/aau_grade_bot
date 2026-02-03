from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import User, UserCredential
from services.credential_service import CredentialService
import uuid

class UserService:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
        self.credential_service = CredentialService()

    async def get_user_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def register_user(self, telegram_id: int, username: Optional[str], 
                            university_id: str, password: str, 
                            campus_id: str, department_id: str) -> User:
        # Check if user exists
        user = await self.get_user_by_telegram_id(telegram_id)
        
        from services.audit_service import AuditService
        audit = AuditService(self.db)

        if not user:
            user = User(
                telegram_id=telegram_id,
                telegram_username=username,
                university_id=university_id,
                campus_id=campus_id,
                department_id=department_id,
                academic_year="Year 1", # Default, updated on first scrape
                semester="Semester : One"
            )
            self.db.add(user)
            await self.db.flush() # Get user.id
            await audit.log("USER_REGISTERED", telegram_id, {"dept": department_id})
            
        # Update/Create credential
        encrypted_pw, iv = self.credential_service.encrypt_password(password)
        
        stmt = select(UserCredential).where(UserCredential.user_id == user.id)
        cred_result = await self.db.execute(stmt)
        credential = cred_result.scalar_one_or_none()
        
        if not credential:
            credential = UserCredential(
                user_id=user.id,
                encrypted_password=encrypted_pw,
                iv=iv
            )
            self.db.add(credential)
        else:
            credential.encrypted_password = encrypted_pw
            credential.iv = iv
            user.is_credential_valid = True # Reset on update
            await audit.log("PASSWORD_UPDATED", telegram_id)
            
        return user

    async def update_academic_status(self, telegram_id: int, year: Optional[str] = None, semester: Optional[str] = None):
        user = await self.get_user_by_telegram_id(telegram_id)
        if user:
            if year:
                user.academic_year = year
            if semester:
                user.semester = semester
            await self.db.flush()
            
            from services.audit_service import AuditService
            await AuditService(self.db).log("ACADEMIC_STATUS_UPDATED", telegram_id, {"year": year, "sem": semester})
        return user

    async def update_university_id(self, telegram_id: int, new_uni_id: str):
        user = await self.get_user_by_telegram_id(telegram_id)
        if user:
            user.university_id = new_uni_id
            await self.db.flush()
            
            from services.audit_service import AuditService
            await AuditService(self.db).log("UNIVERSITY_ID_UPDATED", telegram_id, {"new_id": new_uni_id})
        return user

    async def get_decrypted_password(self, user: User) -> Optional[str]:
        stmt = select(UserCredential).where(UserCredential.user_id == user.id)
        result = await self.db.execute(stmt)
        credential = result.scalar_one_or_none()
        
        if not credential:
            return None
            
        return self.credential_service.decrypt_password(
            credential.encrypted_password, 
            credential.iv
        )
