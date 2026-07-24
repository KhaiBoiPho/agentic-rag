"""FastAPI dependency injection helpers."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.auth.jwt_handler import JWTHandler
from app.db.postgres.models import User
from app.db.postgres.repositories.user_repo import UserRepository

bearer = HTTPBearer()
jwt = JWTHandler()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer)],
) -> User:
    token = credentials.credentials
    payload = jwt.decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    repo = UserRepository()
    user = await repo.get_by_id(user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


# Headers for every SSE (text/event-stream) endpoint. `no-transform` is the
# important one: without it Next.js's default response compression (compress:
# true) gzips the proxied stream, which buffers it to compress — sparse
# events (e.g. Research's step updates, seconds apart) then never flush until
# the whole stream ends, so the browser sees everything at once instead of
# streaming. `no-transform` tells the compressor to leave the body alone;
# `X-Accel-Buffering: no` disables the same buffering in nginx if fronted.
SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
}
