"""
FastAPI router for user authentication endpoints.
Includes email/password auth and Google/Facebook OAuth via fastapi-users.
"""

from fastapi import APIRouter, HTTPException
from starlette.responses import RedirectResponse

from src.auth.manager import auth_backend, oauth_auth_backend, fastapi_users
from src.auth.oauth import google_oauth_client, facebook_oauth_client
from src.auth.schemas import UserCreate, UserRead, UserUpdate
from src.config import settings

from fastapi_users.router.oauth import (
    CSRF_TOKEN_COOKIE_NAME,
    CSRF_TOKEN_KEY,
    generate_csrf_token,
    generate_state_token,
)

def _oauth_redirect(url: str, csrf_token: str) -> RedirectResponse:
    response = RedirectResponse(url=url, status_code=302)
    response.set_cookie(
        CSRF_TOKEN_COOKIE_NAME,
        csrf_token,
        max_age=3600,
        path="/",
        secure=settings.app_base_url.startswith("https://"),
        httponly=True,
        samesite="lax",
    )
    return response

router = APIRouter()

# ─── Email/Password Auth ─────────────────────────────────

router.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth/jwt",
    tags=["auth"],
)

router.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
)

router.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"],
)

# ─── Google OAuth ─────────────────────────────────────────

router.include_router(
    fastapi_users.get_oauth_router(
        google_oauth_client,
        oauth_auth_backend,
        state_secret=settings.encryption_key,
        redirect_url=f"{settings.app_base_url}/auth/google/callback",
        associate_by_email=True,
        is_verified_by_default=True,
        csrf_token_cookie_secure=settings.environment == "production",
    ),
    prefix="/auth/google",
    tags=["auth"],
)

# ─── Facebook OAuth ──────────────────────────────────────

router.include_router(
    fastapi_users.get_oauth_router(
        facebook_oauth_client,
        oauth_auth_backend,
        state_secret=settings.encryption_key,
        redirect_url=f"{settings.app_base_url}/auth/facebook/callback",
        associate_by_email=True,
        is_verified_by_default=True,
        csrf_token_cookie_secure=settings.environment == "production",
    ),
    prefix="/auth/facebook",
    tags=["auth"],
)


def _callback_url(provider: str) -> str:
    return f"{settings.app_base_url}/auth/{provider}/callback"


async def _browser_authorize(oauth_client, provider: str):
    if not oauth_client.client_id or not oauth_client.client_secret:
        raise HTTPException(status_code=400, detail=f"{provider.title()} OAuth not configured")

    csrf_token = generate_csrf_token()
    state = generate_state_token({CSRF_TOKEN_KEY: csrf_token}, settings.encryption_key)
    authorization_url = await oauth_client.get_authorization_url(
        _callback_url(provider),
        state,
    )
    return _oauth_redirect(authorization_url, csrf_token)


@router.get("/auth/google/browser", include_in_schema=False)
async def google_browser_authorize():
    return await _browser_authorize(google_oauth_client, "google")


@router.get("/auth/facebook/browser", include_in_schema=False)
async def facebook_browser_authorize():
    return await _browser_authorize(facebook_oauth_client, "facebook")
