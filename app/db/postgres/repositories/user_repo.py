from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.postgres.base import get_session
from app.db.postgres.models import RefreshToken, User


class UserRepository:
    async def get_by_id(self, user_id: str) -> User | None:
        async with get_session() as s:
            return await s.get(User, uuid.UUID(user_id))

    async def get_by_email(self, email: str) -> User | None:
        async with get_session() as s:
            result = await s.execute(select(User).where(User.email == email))
            return result.scalar_one_or_none()

    async def create(self, email: str, hashed_password: str, full_name: str = "",
                     oauth_provider: str | None = None, oauth_id: str | None = None) -> User:
        async with get_session() as s:
            user = User(
                email=email,
                hashed_password=hashed_password,
                full_name=full_name,
                oauth_provider=oauth_provider,
                oauth_id=oauth_id,
            )
            s.add(user)
            await s.flush()
            await s.refresh(user)
            return user

    # ─── Refresh token management ─────────────────────────────────────────────

    async def store_refresh_token(self, user_id: uuid.UUID, token: str) -> None:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        from app.config import settings
        expires = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
        async with get_session() as s:
            rt = RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires)
            s.add(rt)

    async def refresh_token_valid(self, user_id: str, token: str) -> bool:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        async with get_session() as s:
            result = await s.execute(
                select(RefreshToken).where(
                    RefreshToken.user_id == uuid.UUID(user_id),
                    RefreshToken.token_hash == token_hash,
                    RefreshToken.is_revoked.is_(False),
                    RefreshToken.expires_at > datetime.now(timezone.utc),
                )
            )
            return result.scalar_one_or_none() is not None

    async def revoke_refresh_token(self, user_id: str, token: str) -> None:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        async with get_session() as s:
            result = await s.execute(
                select(RefreshToken).where(
                    RefreshToken.user_id == uuid.UUID(user_id),
                    RefreshToken.token_hash == token_hash,
                )
            )
            rt = result.scalar_one_or_none()
            if rt:
                rt.is_revoked = True
