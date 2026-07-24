"""JWT access + refresh token management with blacklist support."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt

from app.config import settings

_ACCESS_TYPE = "access"
_REFRESH_TYPE = "refresh"


class JWTHandler:
    def create_access_token(self, data: dict[str, Any]) -> str:
        expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
        payload = {**data, "exp": expire, "type": _ACCESS_TYPE, "jti": str(uuid.uuid4())}
        return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    def create_refresh_token(self, data: dict[str, Any]) -> str:
        expire = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
        payload = {**data, "exp": expire, "type": _REFRESH_TYPE, "jti": str(uuid.uuid4())}
        return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    def decode_access_token(self, token: str) -> dict | None:
        return self._decode(token, _ACCESS_TYPE)

    def decode_refresh_token(self, token: str) -> dict | None:
        return self._decode(token, _REFRESH_TYPE)

    def _decode(self, token: str, expected_type: str) -> dict | None:
        try:
            payload = jwt.decode(
                token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
            )
            if payload.get("type") != expected_type:
                return None
            return payload
        except JWTError:
            return None
