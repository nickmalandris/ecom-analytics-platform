"""
User-facing OAuth 2.0 authorization endpoints.
"""

import hmac
import hashlib
import logging
import time
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx
import psycopg2
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import RedirectResponse, JSONResponse

from src.config import settings
from src.auth.encryption import encrypt_token

router = APIRouter(tags=["auth"])  # Prefix handled by main app mount
logger = logging.getLogger(__name__)


def get_db_conn():
    conn = psycopg2.connect(settings.database_url)
    try:
        yield conn
    finally:
        conn.close()


# ─── Shopify OAuth ──────────────────────────────────────

@router.get("/shopify/initiate/{tenant_id}")
def initiate_shopify_auth(tenant_id: int, shop: str, conn=Depends(get_db_conn)):
    """
    Start Shopify OAuth flow.
    Args:
        shop: The shop domain (e.g. my-store.myshopify.com)
    """
    if not settings.shopify_client_id:
        raise HTTPException(status_code=500, detail="Shopify Client ID not configured")

    # Verify tenant exists
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM public.tenants WHERE id = %s", (tenant_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Tenant not found")

    redirect_uri = f"{settings.app_base_url}/api/auth/shopify/callback"
    scopes = "read_products,read_orders,read_customers,read_draft_orders"
    state = str(tenant_id)

    # https://{shop}.myshopify.com/admin/oauth/authorize
    auth_url = f"https://{shop}/admin/oauth/authorize?client_id={settings.shopify_client_id}&scope={scopes}&redirect_uri={redirect_uri}&state={state}"
    
    return RedirectResponse(auth_url)


@router.get("/shopify/callback")
async def shopify_auth_callback(request: Request):
    """
    Handle Shopify OAuth callback.
    Exchanges code for permanent access token.
    """
    params = dict(request.query_params)
    code = params.get("code")
    shop = params.get("shop")
    state = params.get("state")
    timestamp = params.get("timestamp")
    signature = params.get("hmac")

    if not code or not shop or not state or not signature or not timestamp:
        raise HTTPException(status_code=400, detail="Missing parameters")

    # Verify HMAC
    # Remove hmac from params and sort keys
    message = "&".join([f"{k}={params[k]}" for k in sorted(params) if k != "hmac"])
    secret = settings.shopify_secret_key.encode()
    digest = hmac.new(secret, message.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(digest, signature):
        raise HTTPException(status_code=400, detail="Invalid HMAC signature")

    # Verify timestamp (replay attack prevention)
    if int(time.time()) - int(timestamp) > 3600:
        raise HTTPException(status_code=400, detail="Request expired")

    tenant_id = int(state)

    # Exchange code for token
    token_url = f"https://{shop}/admin/oauth/access_token"
    async with httpx.AsyncClient() as client:
        resp = await client.post(token_url, json={
            "client_id": settings.shopify_client_id,
            "client_secret": settings.shopify_secret_key,
            "code": code
        })
        
        if resp.status_code != 200:
            logger.error(f"Shopify token exchange failed: {resp.text}")
            raise HTTPException(status_code=400, detail="Token exchange failed")
        
        data = resp.json()
        access_token = data.get("access_token")

    # Store encrypted token
    encrypted = encrypt_token(access_token)
    
    conn = psycopg2.connect(settings.database_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE public.tenants 
                SET shopify_access_token = %s, 
                    shopify_store_url = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (encrypted, shop, tenant_id)
            )
        conn.commit()
    finally:
        conn.close()

    return JSONResponse(content={"status": "success", "message": "Shopify connected successfully"})


# ─── Meta OAuth ─────────────────────────────────────────

@router.get("/meta/initiate/{tenant_id}")
def initiate_meta_auth(tenant_id: int, conn=Depends(get_db_conn)):
    """Start Meta OAuth flow."""
    if not settings.meta_app_id:
        raise HTTPException(status_code=500, detail="Meta App ID not configured")

    # Verify tenant
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM public.tenants WHERE id = %s", (tenant_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Tenant not found")

    redirect_uri = f"{settings.app_base_url}/api/auth/meta/callback"
    scope = "ads_read,read_insights,business_management"
    state = str(tenant_id)

    auth_url = (
        f"https://www.facebook.com/v18.0/dialog/oauth?"
        f"client_id={settings.meta_app_id}&redirect_uri={redirect_uri}&state={state}&scope={scope}"
    )
    
    return RedirectResponse(auth_url)


@router.get("/meta/callback")
async def meta_auth_callback(code: str, state: str):
    """
    Handle Meta OAuth callback.
    Exchanges code -> short-lived token -> long-lived token.
    """
    tenant_id = int(state)
    redirect_uri = f"{settings.app_base_url}/api/auth/meta/callback"

    async with httpx.AsyncClient() as client:
        # 1. Exchange code for short-lived token
        token_url = "https://graph.facebook.com/v18.0/oauth/access_token"
        resp = await client.get(token_url, params={
            "client_id": settings.meta_app_id,
            "redirect_uri": redirect_uri,
            "client_secret": settings.meta_app_secret,
            "code": code
        })

        if resp.status_code != 200:
            logger.error(f"Meta token exchange failed: {resp.text}")
            raise HTTPException(status_code=400, detail="Token exchange failed")
        
        data = resp.json()
        short_token = data.get("access_token")

        # 2. Exchange short-lived for long-lived token
        exchange_url = "https://graph.facebook.com/v18.0/oauth/access_token"
        resp = await client.get(exchange_url, params={
            "grant_type": "fb_exchange_token",
            "client_id": settings.meta_app_id,
            "client_secret": settings.meta_app_secret,
            "fb_exchange_token": short_token
        })

        if resp.status_code != 200:
            logger.error(f"Meta long-lived token exchange failed: {resp.text}")
            raise HTTPException(status_code=400, detail="Long-lived token exchange failed")

        data = resp.json()
        long_token = data.get("access_token")
        expires_in = data.get("expires_in", 5184000) # Default ~60 days

    # Store encrypted token
    encrypted = encrypt_token(long_token)
    expires_at = datetime.now() + timedelta(seconds=expires_in)

    conn = psycopg2.connect(settings.database_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE public.tenants 
                SET meta_access_token = %s,
                    meta_token_expires_at = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (encrypted, expires_at, tenant_id)
            )
        conn.commit()
    finally:
        conn.close()

    return JSONResponse(content={"status": "success", "message": "Meta connected successfully"})
