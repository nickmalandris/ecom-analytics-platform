"""
Pydantic schemas for user authentication.
"""

from fastapi_users import schemas


class UserRead(schemas.BaseUser[int]):
    tenant_id: int | None = None


class UserCreate(schemas.BaseUserCreate):
    tenant_id: int | None = None


class UserUpdate(schemas.BaseUserUpdate):
    tenant_id: int | None = None
