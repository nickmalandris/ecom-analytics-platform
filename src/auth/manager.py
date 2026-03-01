"""
User manager for FastAPI Users.
Handles registration, authentication, and password management.
"""

from typing import Optional

from fastapi import Depends, Request
from fastapi.responses import Response
from starlette.responses import RedirectResponse
from fastapi_users import BaseUserManager, FastAPIUsers, IntegerIDMixin
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    CookieTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase

from src.auth.db import User, get_user_db
from src.config import settings

SECRET = settings.encryption_key  # Reuse our encryption key for JWT signing


class UserManager(IntegerIDMixin, BaseUserManager[User, int]):
    reset_password_token_secret = SECRET
    verification_token_secret = SECRET

    async def on_after_register(self, user: User, request: Optional[Request] = None):
        print(f"User {user.id} has registered.")

    async def on_after_forgot_password(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        print(f"User {user.id} has forgot their password. Reset token: {token}")

    async def on_after_request_verify(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        print(f"Verification requested for user {user.id}. Verification token: {token}")


async def get_user_manager(user_db: SQLAlchemyUserDatabase = Depends(get_user_db)):
    yield UserManager(user_db)


# ─── Authentication Backends ─────────────────────────────

# Cookie settings for the OAuth redirect flow (browser top-level navigation).
_cookie_kwargs = dict(
    cookie_name="analytics_auth",
    cookie_max_age=3600,
    cookie_secure=settings.environment == "production",
    cookie_samesite="none" if settings.environment == "production" else "lax",
)


class RedirectCookieTransport(CookieTransport):
    """CookieTransport that redirects to the frontend after login.

    Used exclusively for the OAuth callback flow where the browser arrives via
    a redirect from the identity provider and needs to be sent to the frontend
    app with the auth cookie already set on the response.
    """

    def __init__(self, redirect_url: str, **kwargs):
        super().__init__(**kwargs)
        self.redirect_url = redirect_url

    async def get_login_response(self, token: str) -> Response:
        response = RedirectResponse(url=self.redirect_url, status_code=302)
        return self._set_login_cookie(response, token)


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=SECRET, lifetime_seconds=3600)


# 1) Bearer transport — returns JSON {"access_token": "...", "token_type": "bearer"}
#    Used for email/password login (AJAX). The frontend stores the token in
#    localStorage and sends it via the Authorization header on every request.
bearer_transport = BearerTransport(tokenUrl="/auth/jwt/login")

auth_backend = AuthenticationBackend(
    name="jwt_bearer",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

# 2) Redirect cookie transport — returns 302 to frontend with Set-Cookie
#    Used for the OAuth callback flow (Google/Facebook) where the browser
#    arrives via a top-level redirect and cookies are first-party.
oauth_cookie_transport = RedirectCookieTransport(
    redirect_url=settings.frontend_url,
    **_cookie_kwargs,
)

oauth_auth_backend = AuthenticationBackend(
    name="jwt_cookie_oauth",
    transport=oauth_cookie_transport,
    get_strategy=get_jwt_strategy,
)

# FastAPIUsers needs all backends so current_user() can authenticate via
# either the Authorization header (bearer) or the cookie (OAuth sessions).
fastapi_users = FastAPIUsers[User, int](get_user_manager, [auth_backend, oauth_auth_backend])

current_active_user = fastapi_users.current_user(active=True)
