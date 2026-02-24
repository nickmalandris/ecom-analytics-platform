"""
FastAPI router for user authentication endpoints.
"""

from fastapi import APIRouter

from src.auth.manager import auth_backend, fastapi_users
from src.auth.schemas import UserCreate, UserRead, UserUpdate

router = APIRouter()

# Authentication routes (login/logout)
router.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth/jwt",
    tags=["auth"],
)

# Registration routes
router.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
)

# User management routes (get current user, update user)
router.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"],
)
