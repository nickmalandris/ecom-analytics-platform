"""
Connection status API endpoints.
"""

import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Body
import psycopg2
from pydantic import BaseModel

from src.api.auth import resolve_tenant
from src.auth.manager import current_active_user
from src.auth.db import User
from src.config import settings
from src.ingestion.db_utils import create_tenant_schema_and_tables

router = APIRouter(prefix="/connections", tags=["connections"])
logger = logging.getLogger(__name__)

def get_db_url():
    return settings.database_url

def _generate_api_key() -> str:
    return f"sk_{secrets.token_hex(24)}"

class ConnectShopifyRequest(BaseModel):
    shopify_store_url: str

@router.get("/status")
async def get_connection_status(user: User = Depends(current_active_user)):
    """
    Get the connection status for the current user's tenant.
    """
    if not user.tenant_id:
        return {
            "shopify": {"connected": False},
            "meta": {"connected": False},
            "tenant_id": None
        }

    conn = psycopg2.connect(get_db_url())
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT shopify_store_url, shopify_access_token, 
                       meta_account_id, meta_access_token 
                FROM public.tenants 
                WHERE id = %s
                """,
                (user.tenant_id,)
            )
            row = cur.fetchone()
            
            if not row:
                # Should ideally not happen if user.tenant_id is set
                return {
                    "shopify": {"connected": False},
                    "meta": {"connected": False},
                    "tenant_id": user.tenant_id
                }
                
            shopify_url, shopify_token, meta_id, meta_token = row
            
            return {
                "shopify": {
                    "connected": bool(shopify_url and shopify_token),
                    "store_url": shopify_url
                },
                "meta": {
                    "connected": bool(meta_id and meta_token),
                    "account_id": meta_id
                },
                "tenant_id": user.tenant_id
            }
    finally:
        conn.close()


@router.post("/shopify/initiate")
async def initiate_shopify_connection(
    body: ConnectShopifyRequest,
    user: User = Depends(current_active_user)
):
    """
    Initiate Shopify connection.
    If user has no tenant, creates one and links it.
    If user has a tenant, updates the shop URL.
    Returns the OAuth redirect URL.
    """
    shop_url = body.shopify_store_url.strip()
    if not shop_url:
        raise HTTPException(status_code=400, detail="Store URL is required")

    # Normalize domain
    if "://" in shop_url:
        shop_url = shop_url.split("://")[1]
    shop_url = shop_url.split("/")[0]

    conn = psycopg2.connect(get_db_url())
    tenant_id = user.tenant_id
    
    try:
        with conn.cursor() as cur:
            if not tenant_id:
                # 1. Create new tenant
                logger.info(f"Creating new tenant for user {user.id}, shop {shop_url}")
                api_key = _generate_api_key()
                
                # Check if a tenant already exists for this shop (to avoid duplicates)
                # In a real app, you might want to claim it or error out.
                # Here we'll just create a new one or attach if found?
                # Let's create new for now to be safe, or check uniqueness.
                cur.execute("SELECT id FROM public.tenants WHERE shopify_store_url = %s", (shop_url,))
                existing_tenant = cur.fetchone()
                
                if existing_tenant:
                    tenant_id = existing_tenant[0]
                    logger.info(f"Found existing tenant {tenant_id} for shop {shop_url}, linking to user {user.id}")
                else:
                    cur.execute(
                        """
                        INSERT INTO public.tenants (name, shopify_store_url, api_key)
                        VALUES (%s, %s, %s)
                        RETURNING id
                        """,
                        (shop_url, shop_url, api_key)
                    )
                    tenant_id = cur.fetchone()[0]
                    # Create schema and tables for new tenant
                    create_tenant_schema_and_tables(conn, tenant_id)

                # 2. Link tenant to user
                # We need to update the users table.
                # Since we are using SQLAlchemy for users but raw psycopg2 here, we just run SQL.
                cur.execute(
                    "UPDATE users SET tenant_id = %s WHERE id = %s",
                    (tenant_id, user.id)
                )
            else:
                # User already has a tenant, update the shop URL if changed
                # (Re-connection scenario)
                logger.info(f"User {user.id} already has tenant {tenant_id}. Updating shop URL.")
                cur.execute(
                    "UPDATE public.tenants SET shopify_store_url = %s WHERE id = %s",
                    (shop_url, tenant_id)
                )

        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to initiate Shopify connection: {e}")
        raise HTTPException(status_code=500, detail="Failed to initialize connection")
    finally:
        conn.close()

    # Construct the auth initiation URL
    # We redirect to our existing auth flow
    redirect_url = f"{settings.app_base_url}/api/auth/shopify/initiate/{tenant_id}?shop={shop_url}"
    
    return {"redirect_url": redirect_url}
