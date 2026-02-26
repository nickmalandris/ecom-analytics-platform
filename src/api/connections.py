"""
Connection status and connect/sync API endpoints.
"""

import logging
import secrets

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
import psycopg2
from pydantic import BaseModel

from src.auth.manager import current_active_user
from src.auth.db import User
from src.config import settings
from src.ingestion.db_utils import create_tenant_schema_and_tables

router = APIRouter(prefix="/connections", tags=["connections"])
logger = logging.getLogger(__name__)


def _get_conn():
    return psycopg2.connect(settings.database_url)


def _generate_api_key() -> str:
    return f"sk_{secrets.token_hex(24)}"


class ConnectShopifyRequest(BaseModel):
    shopify_store_url: str


# ── Status ───────────────────────────────────────────────


@router.get("/status")
async def get_connection_status(user: User = Depends(current_active_user)):
    """Get the connection status for the current user's tenant."""
    if not user.tenant_id:
        return {
            "shopify": {"connected": False},
            "meta": {"connected": False},
            "tenant_id": None,
        }

    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT shopify_store_url, shopify_access_token,
                       meta_account_id, meta_access_token
                FROM public.tenants
                WHERE id = %s
                """,
                (user.tenant_id,),
            )
            row = cur.fetchone()

            if not row:
                return {
                    "shopify": {"connected": False},
                    "meta": {"connected": False},
                    "tenant_id": user.tenant_id,
                }

            shopify_url, shopify_token, meta_id, meta_token = row

            return {
                "shopify": {
                    "connected": bool(shopify_url and shopify_token),
                    "store_url": shopify_url,
                },
                "meta": {
                    "connected": bool(meta_id and meta_token),
                    "account_id": meta_id,
                },
                "tenant_id": user.tenant_id,
            }
    finally:
        conn.close()


@router.get("/sync-status")
async def get_sync_status(user: User = Depends(current_active_user)):
    """
    Get sync progress for the current user's tenant.
    Returns per-resource status so the frontend can track ingestion progress.
    """
    if not user.tenant_id:
        return {"syncing": False, "resources": []}

    conn = _get_conn()
    try:
        from src.ingestion.sync_state import ensure_sync_state_table, get_sync_status as _get_status

        ensure_sync_state_table(conn)
        resources = _get_status(conn, user.tenant_id)

        # Determine overall sync state
        any_running = any(r["status"] == "running" for r in resources)
        all_completed = len(resources) > 0 and all(
            r["status"] in ("completed", "idle") for r in resources
        )
        any_failed = any(r["status"] == "failed" for r in resources)

        return {
            "syncing": any_running,
            "completed": all_completed,
            "failed": any_failed,
            "resources": resources,
        }
    finally:
        conn.close()


# ── Connect + Sync ───────────────────────────────────────


def _run_shopify_sync(tenant_id: int):
    """Background task: run full Shopify sync for a tenant."""
    try:
        from src.ingestion.shopify_sync import full_sync
        full_sync(tenant_id)
    except Exception as e:
        logger.error("Background Shopify sync failed for tenant %s: %s", tenant_id, e)


@router.post("/shopify/connect")
async def connect_shopify(
    body: ConnectShopifyRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(current_active_user),
):
    """
    All-in-one Shopify connect endpoint.
    1. Creates tenant if needed (or finds existing)
    2. Ensures schema + tables
    3. Kicks off full data sync in background
    4. Returns immediately — frontend polls /sync-status

    NOTE: This bypasses OAuth for stores that already have a token stored
    (e.g. the dev store). For production OAuth flow, use /shopify/initiate.
    """
    shop_url = body.shopify_store_url.strip()
    if not shop_url:
        raise HTTPException(status_code=400, detail="Store URL is required")

    # Normalize domain
    if "://" in shop_url:
        shop_url = shop_url.split("://")[1]
    shop_url = shop_url.split("/")[0]

    conn = _get_conn()
    tenant_id = user.tenant_id

    try:
        with conn.cursor() as cur:
            if not tenant_id:
                logger.info("Creating tenant for user %s, shop %s", user.id, shop_url)
                api_key = _generate_api_key()

                # Check for existing tenant with this shop
                cur.execute(
                    "SELECT id FROM public.tenants WHERE shopify_store_url = %s",
                    (shop_url,),
                )
                existing = cur.fetchone()

                if existing:
                    tenant_id = existing[0]
                    logger.info("Found existing tenant %s for shop %s", tenant_id, shop_url)
                else:
                    cur.execute(
                        """
                        INSERT INTO public.tenants (name, shopify_store_url, api_key)
                        VALUES (%s, %s, %s)
                        RETURNING id
                        """,
                        (shop_url, shop_url, api_key),
                    )
                    tenant_id = cur.fetchone()[0]

                # Link user to tenant
                cur.execute(
                    "UPDATE users SET tenant_id = %s WHERE id = %s",
                    (tenant_id, user.id),
                )
            else:
                # User already has tenant — update shop URL if needed
                cur.execute(
                    "UPDATE public.tenants SET shopify_store_url = %s WHERE id = %s",
                    (shop_url, tenant_id),
                )

            # Ensure schema + tables exist
            create_tenant_schema_and_tables(conn, tenant_id)

        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error("Failed to connect Shopify: %s", e)
        raise HTTPException(status_code=500, detail="Failed to initialize connection")
    finally:
        conn.close()

    # Check if this tenant already has a Shopify token
    conn2 = _get_conn()
    try:
        with conn2.cursor() as cur:
            cur.execute(
                "SELECT shopify_access_token FROM public.tenants WHERE id = %s",
                (tenant_id,),
            )
            row = cur.fetchone()
            has_token = bool(row and row[0])
    finally:
        conn2.close()

    if has_token:
        # Token exists — sync directly in background
        logger.info("Tenant %s has Shopify token, starting background sync", tenant_id)
        background_tasks.add_task(_run_shopify_sync, tenant_id)
        return {"status": "syncing", "tenant_id": tenant_id}
    else:
        # No token — need OAuth
        redirect_url = (
            f"{settings.app_base_url}/api/auth/shopify/initiate/{tenant_id}?shop={shop_url}"
        )
        return {"status": "needs_oauth", "redirect_url": redirect_url, "tenant_id": tenant_id}


# ── Legacy initiate (kept for OAuth flow) ────────────────


@router.post("/shopify/initiate")
async def initiate_shopify_connection(
    body: ConnectShopifyRequest,
    user: User = Depends(current_active_user),
):
    """Legacy: Initiate Shopify OAuth connection. Returns redirect URL."""
    shop_url = body.shopify_store_url.strip()
    if not shop_url:
        raise HTTPException(status_code=400, detail="Store URL is required")

    if "://" in shop_url:
        shop_url = shop_url.split("://")[1]
    shop_url = shop_url.split("/")[0]

    conn = _get_conn()
    tenant_id = user.tenant_id

    try:
        with conn.cursor() as cur:
            if not tenant_id:
                api_key = _generate_api_key()
                cur.execute(
                    "SELECT id FROM public.tenants WHERE shopify_store_url = %s",
                    (shop_url,),
                )
                existing = cur.fetchone()

                if existing:
                    tenant_id = existing[0]
                    create_tenant_schema_and_tables(conn, tenant_id)
                else:
                    cur.execute(
                        """
                        INSERT INTO public.tenants (name, shopify_store_url, api_key)
                        VALUES (%s, %s, %s)
                        RETURNING id
                        """,
                        (shop_url, shop_url, api_key),
                    )
                    tenant_id = cur.fetchone()[0]
                    create_tenant_schema_and_tables(conn, tenant_id)

                cur.execute(
                    "UPDATE users SET tenant_id = %s WHERE id = %s",
                    (tenant_id, user.id),
                )
            else:
                cur.execute(
                    "UPDATE public.tenants SET shopify_store_url = %s WHERE id = %s",
                    (shop_url, tenant_id),
                )

        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error("Failed to initiate Shopify connection: %s", e)
        raise HTTPException(status_code=500, detail="Failed to initialize connection")
    finally:
        conn.close()

    redirect_url = (
        f"{settings.app_base_url}/api/auth/shopify/initiate/{tenant_id}?shop={shop_url}"
    )
    return {"redirect_url": redirect_url}
