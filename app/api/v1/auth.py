"""Auth endpoints — register, login, refresh, logout, OAuth2."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr

from app.core.auth.jwt_handler import JWTHandler
from app.core.auth.oauth import OAuthProvider
from app.core.auth.password import PasswordHandler
from app.db.postgres.repositories.user_repo import UserRepository

router = APIRouter()
jwt = JWTHandler()
pw = PasswordHandler()
oauth = OAuthProvider()


# ─── Schemas ─────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str = ""


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest):
    repo = UserRepository()
    if await repo.get_by_email(body.email):
        raise HTTPException(status_code=409, detail="Email already registered")

    hashed = pw.hash(body.password)
    user = await repo.create(
        email=body.email,
        hashed_password=hashed,
        full_name=body.full_name,
    )
    access = jwt.create_access_token({"sub": str(user.id), "email": user.email})
    refresh = jwt.create_refresh_token({"sub": str(user.id)})
    await repo.store_refresh_token(user.id, refresh)
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    repo = UserRepository()
    user = await repo.get_by_email(body.email)
    if not user or not pw.verify(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    access = jwt.create_access_token({"sub": str(user.id), "email": user.email})
    refresh = jwt.create_refresh_token({"sub": str(user.id)})
    await repo.store_refresh_token(user.id, refresh)
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest):
    payload = jwt.decode_refresh_token(body.refresh_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    repo = UserRepository()
    user_id = payload["sub"]

    # Blacklist check — token must exist and not be revoked
    if not await repo.refresh_token_valid(user_id, body.refresh_token):
        raise HTTPException(status_code=401, detail="Token revoked")

    user = await repo.get_by_id(user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Inactive user")

    # Rotate refresh token
    await repo.revoke_refresh_token(user_id, body.refresh_token)
    new_access = jwt.create_access_token({"sub": str(user.id), "email": user.email})
    new_refresh = jwt.create_refresh_token({"sub": str(user.id)})
    await repo.store_refresh_token(user.id, new_refresh)
    return TokenResponse(access_token=new_access, refresh_token=new_refresh)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshRequest):
    payload = jwt.decode_refresh_token(body.refresh_token)
    if payload:
        repo = UserRepository()
        await repo.revoke_refresh_token(payload["sub"], body.refresh_token)


# ─── OAuth2 ──────────────────────────────────────────────────────────────────

@router.get("/oauth/google")
async def oauth_google_redirect():
    url = oauth.google_authorization_url()
    return RedirectResponse(url)


@router.get("/oauth/google/callback", response_model=TokenResponse)
async def oauth_google_callback(code: str, state: str = ""):
    user_info = await oauth.google_exchange(code)
    return await _oauth_login_or_register(user_info, "google")


@router.get("/oauth/github")
async def oauth_github_redirect():
    url = oauth.github_authorization_url()
    return RedirectResponse(url)


@router.get("/oauth/github/callback", response_model=TokenResponse)
async def oauth_github_callback(code: str):
    user_info = await oauth.github_exchange(code)
    return await _oauth_login_or_register(user_info, "github")


async def _oauth_login_or_register(user_info: dict, provider: str) -> TokenResponse:
    repo = UserRepository()
    email = user_info.get("email", "")
    if not email:
        raise HTTPException(status_code=400, detail="OAuth provider did not return email")

    user = await repo.get_by_email(email)
    if not user:
        user = await repo.create(
            email=email,
            hashed_password="",  # no password for OAuth users
            full_name=user_info.get("name", ""),
            oauth_provider=provider,
            oauth_id=str(user_info.get("id", "")),
        )

    access = jwt.create_access_token({"sub": str(user.id), "email": user.email})
    refresh = jwt.create_refresh_token({"sub": str(user.id)})
    await repo.store_refresh_token(user.id, refresh)
    return TokenResponse(access_token=access, refresh_token=refresh)
