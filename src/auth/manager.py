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
    JWTStrategy,
    Transport,
)
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users.authentication.transport.base import TransportLogoutNotSupportedError
from fastapi_users.openapi import OpenAPIResponseType

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


class RedirectBearerTransport(Transport):
    """Transport that redirects to the frontend with the token in a query param.

    Used for the OAuth callback flow where the browser arrives via a top-level
    redirect from the identity provider.  Instead of setting a cookie (which
    would be blocked as a third-party cookie in cross-origin deployments), the
    JWT is appended to the redirect URL as ``?token=<jwt>``.  The frontend
    reads the token, stores it in localStorage, and strips it from the URL.
    """

    scheme = None  # type: ignore[assignment]  # not used for OAuth flow

    def __init__(self, redirect_url: str):
        self.redirect_url = redirect_url

    async def get_login_response(self, token: str) -> Response:
        url = f"{self.redirect_url}?token={token}"
        return RedirectResponse(url=url, status_code=302)

    async def get_logout_response(self) -> Response:
        raise TransportLogoutNotSupportedError()

    @staticmethod
    def get_openapi_login_responses_success() -> OpenAPIResponseType:
        return {}

    @staticmethod
    def get_openapi_logout_responses_success() -> OpenAPIResponseType:
        return {}


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

# 2) Redirect bearer transport — returns 302 to frontend with token in URL
#    Used for the OAuth callback flow (Google/Facebook). Avoids third-party
#    cookie issues entirely by passing the JWT via the redirect URL.
oauth_redirect_transport = RedirectBearerTransport(
    redirect_url=settings.frontend_url,
)

oauth_auth_backend = AuthenticationBackend(
    name="jwt_redirect",
    transport=oauth_redirect_transport,
    get_strategy=get_jwt_strategy,
)

# FastAPIUsers needs all backends so current_user() can authenticate via
# either the Authorization header (bearer) or the redirect token (OAuth).
fastapi_users = FastAPIUsers[User, int](get_user_manager, [auth_backend, oauth_auth_backend])

current_active_user = fastapi_users.current_user(active=True)
