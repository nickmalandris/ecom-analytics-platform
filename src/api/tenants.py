"""
Tenant CRUD API endpoints.

All endpoints require admin API key except GET /tenants/me (own tenant).
"""

import os
import secrets

import psycopg2
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException

from src.api.auth import require_admin, resolve_tenant
from src.api.schemas import TenantCreate, TenantResponse, TenantUpdate

router = APIRouter(prefix="/tenants", tags=["tenants"])

load_dotenv()


def _get_db_url() -> str:
    return os.getenv(
        "DATABASE_URL",
        "postgresql://analytics_user:analytics_pass@localhost:5435/analytics",
    )


def _generate_api_key() -> str:
    """Generate a random API key."""
    return f"sk_{secrets.token_hex(24)}"


def _row_to_tenant(row: tuple) -> TenantResponse:
    return TenantResponse(
        id=row[0],
        name=row[1],
        shopify_store_url=row[2],
        meta_account_id=row[3],
        api_key=row[4],
        email_recipients=row[5] or [],
        created_at=row[6],
        updated_at=row[7],
    )


# ── Tenant-scoped (own data) ────────────────────

@router.get("/me", response_model=TenantResponse)
def get_own_tenant(tenant: dict = Depends(resolve_tenant)):
    """Get the current tenant's info (identified by API key)."""
    if tenant.get("is_admin"):
        raise HTTPException(status_code=400, detail="Admin key has no tenant profile. Use /tenants/{id}.")

    conn = psycopg2.connect(_get_db_url())
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, name, shopify_store_url, meta_account_id, api_key,
                          email_recipients, created_at, updated_at
                   FROM public.tenants WHERE id = %s""",
                (tenant["id"],),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return _row_to_tenant(row)


# ── Admin endpoints ──────────────────────────────

@router.get("", response_model=list[TenantResponse])
def list_tenants(_admin: dict = Depends(require_admin)):
    """List all tenants (admin only)."""
    conn = psycopg2.connect(_get_db_url())
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, name, shopify_store_url, meta_account_id, api_key,
                          email_recipients, created_at, updated_at
                   FROM public.tenants ORDER BY id"""
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    return [_row_to_tenant(r) for r in rows]


@router.get("/{tenant_id}", response_model=TenantResponse)
def get_tenant(tenant_id: int, _admin: dict = Depends(require_admin)):
    """Get a tenant by ID (admin only)."""
    conn = psycopg2.connect(_get_db_url())
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, name, shopify_store_url, meta_account_id, api_key,
                          email_recipients, created_at, updated_at
                   FROM public.tenants WHERE id = %s""",
                (tenant_id,),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return _row_to_tenant(row)


@router.post("", response_model=TenantResponse, status_code=201)
def create_tenant(body: TenantCreate, _admin: dict = Depends(require_admin)):
    """Create a new tenant with schemas (admin only)."""
    api_key = _generate_api_key()
    conn = psycopg2.connect(_get_db_url())
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO public.tenants
                       (name, shopify_store_url, meta_account_id, api_key, email_recipients)
                   VALUES (%s, %s, %s, %s, %s)
                   RETURNING id, name, shopify_store_url, meta_account_id, api_key,
                             email_recipients, created_at, updated_at""",
                (
                    body.name,
                    body.shopify_store_url,
                    body.meta_account_id,
                    api_key,
                    body.email_recipients or None,
                ),
            )
            row = cur.fetchone()
            tenant_id = row[0]

            # Create raw and analytics schemas for the new tenant
            raw_schema = f"raw_tenant_{tenant_id}"
            analytics_schema = f"analytics_tenant_{tenant_id}"
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {raw_schema}")
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {analytics_schema}")

        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

    return _row_to_tenant(row)


@router.patch("/{tenant_id}", response_model=TenantResponse)
def update_tenant(
    tenant_id: int,
    body: TenantUpdate,
    _admin: dict = Depends(require_admin),
):
    """Update a tenant's details (admin only)."""
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clauses = []
    values = []
    for field, value in updates.items():
        set_clauses.append(f"{field} = %s")
        values.append(value)

    set_clauses.append("updated_at = now()")
    values.append(tenant_id)

    conn = psycopg2.connect(_get_db_url())
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""UPDATE public.tenants
                    SET {', '.join(set_clauses)}
                    WHERE id = %s
                    RETURNING id, name, shopify_store_url, meta_account_id, api_key,
                              email_recipients, created_at, updated_at""",
                values,
            )
            row = cur.fetchone()
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return _row_to_tenant(row)


@router.delete("/{tenant_id}", status_code=204)
def delete_tenant(tenant_id: int, _admin: dict = Depends(require_admin)):
    """Delete a tenant and their schemas (admin only)."""
    conn = psycopg2.connect(_get_db_url())
    try:
        with conn.cursor() as cur:
            # Drop schemas
            raw_schema = f"raw_tenant_{tenant_id}"
            analytics_schema = f"analytics_tenant_{tenant_id}"
            cur.execute(f"DROP SCHEMA IF EXISTS {raw_schema} CASCADE")
            cur.execute(f"DROP SCHEMA IF EXISTS {analytics_schema} CASCADE")

            # Delete tenant record
            cur.execute("DELETE FROM public.tenants WHERE id = %s", (tenant_id,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Tenant not found")
        conn.commit()
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
