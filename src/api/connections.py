"""
Connection status API endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
import psycopg2
from src.api.auth import resolve_tenant
from src.auth.manager import current_active_user
from src.auth.db import User
from src.config import settings

router = APIRouter(prefix="/connections", tags=["connections"])

def get_db_url():
    return settings.database_url

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
