"""Registration workflow service."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Protocol, Any

from clients.aau_portal import PortalAuthenticationError
from crypto.cipher import AesGcmCipher, Ciphertext
from dto.bot import RegistrationRequest, RegistrationResult
from utils.validation import normalize_aau_undergraduate_id
from parser.models import ProfilePageResult


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
                    "department": profile.profile.department,
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
                    await uow.commit()
            except Exception as db_exc:
                import logging
                logging.getLogger(__name__).warning(f"Registration DB persistence warning: {db_exc}")

        if self.cache is not None:
            await self.cache.set(f"registration:{request.telegram_id}", "1", ttl_seconds=300)

        return RegistrationOutcome(
            profile=profile,
            result=RegistrationResult(
                success=True, 
                message=f"✅ <b>Registration complete!</b>\n\n"
                        f"University ID: <code>{university_id}</code>\n"
                        f"Department: <code>{profile.profile.department}</code>\n\n"
                        "⚡ <b>Initial Sync Started</b>\n"
                        "I'm now fetching your historical grades from the portal for the first time. This usually takes 1-2 minutes.\n\n"
                        "I'll notify you as soon as I have the results! ⏳"
            ),
        )
