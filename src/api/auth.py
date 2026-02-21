"""
API key authentication middleware.

Tenants authenticate by passing their API key in the X-API-Key header.
An admin key (ADMIN_API_KEY env var) grants access to all endpoints.
"""

import os

import psycopg2
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

load_dotenv()

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")


def _get_db_url() -> str:
    return os.getenv("DATABASE_URL")


def resolve_tenant(api_key: str | None = Security(API_KEY_HEADER)) -> dict:
    """
    Validate the API key and return the tenant record.

    If the key matches ADMIN_API_KEY, returns a synthetic admin tenant
    with id=0 (used for cross-tenant admin endpoints).
    """
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")

    # Admin key bypass
    if api_key == ADMIN_API_KEY:
        return {"id": 0, "name": "Admin", "is_admin": True}

    # Look up tenant by API key
    conn = psycopg2.connect(_get_db_url())
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, email_recipients FROM public.tenants WHERE api_key = %s",
                (api_key,),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=403, detail="Invalid API key")

    return {
        "id": row[0],
        "name": row[1],
        "email_recipients": row[2] or [],
        "is_admin": False,
    }


def require_admin(tenant: dict = Depends(resolve_tenant)) -> dict:
    """Dependency that requires the admin API key."""
    if not tenant.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return tenant
