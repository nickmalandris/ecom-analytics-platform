"""
FastAPI router for user authentication endpoints.
Includes email/password auth and Google/Facebook OAuth via fastapi-users.
"""

from fastapi import APIRouter, Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse

from src.auth.manager import auth_backend, fastapi_users
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
        auth_backend,
        state_secret=settings.encryption_key,
        redirect_url=f"{settings.app_base_url}/auth/google/callback",
        associate_by_email=True,
        is_verified_by_default=True,
        csrf_token_cookie_secure=False,
    ),
    prefix="/auth/google",
    tags=["auth"],
)

# ─── Facebook OAuth ──────────────────────────────────────

router.include_router(
    fastapi_users.get_oauth_router(
        facebook_oauth_client,
        auth_backend,
        state_secret=settings.encryption_key,
        redirect_url=f"{settings.app_base_url}/auth/facebook/callback",
        associate_by_email=True,
        is_verified_by_default=True,
        csrf_token_cookie_secure=False,
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


# ─── OAuth Callback Redirect Middleware ──────────────────
# fastapi-users' CookieTransport returns 204 on the OAuth callback.
# Since this is a browser redirect from Google/Facebook, we need to
# redirect the user to the frontend after the auth cookie is set.

class OAuthCallbackRedirectMiddleware(BaseHTTPMiddleware):
    """After OAuth callback sets the auth cookie (204), redirect to frontend."""

    OAUTH_CALLBACK_PATHS = {"/auth/google/callback", "/auth/facebook/callback"}

    async def dispatch(self, request: Request, call_next):
        try:
            response: Response = await call_next(request)

            if request.url.path in self.OAUTH_CALLBACK_PATHS and response.status_code == 204:
                # Build redirect response preserving the Set-Cookie headers
                redirect = RedirectResponse(url=settings.frontend_url, status_code=302)
                # Copy cookies from the original response (using raw headers since MutableHeaders lacks multi_items)
                for key, value in response.headers.raw:
                    if key.lower() == b"set-cookie":
                        redirect.headers.append("set-cookie", value.decode("latin-1"))
                return redirect

            return response
        except Exception as e:
            import traceback
            err_msg = traceback.format_exc()
            print(f"OAUTH MIDDLEWARE CAUGHT ERROR:\\n{err_msg}")
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=500, content={"error": "Internal Server Error", "detail": str(e), "traceback": err_msg})
