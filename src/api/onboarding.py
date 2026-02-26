"""
Self-service onboarding endpoints.
"""

import logging
import secrets

import psycopg2
from fastapi import APIRouter, Request, HTTPException, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from src.config import settings
from src.ingestion.db_utils import create_tenant_schema_and_tables

router = APIRouter(prefix="/onboarding", tags=["onboarding"])
logger = logging.getLogger(__name__)

# Setup templates
templates = Jinja2Templates(directory="src/ui/templates")

class ShopifyConnectRequest(BaseModel):
    shopify_store_url: str

def get_db_url():
    return settings.database_url

def _generate_api_key() -> str:
    return f"sk_{secrets.token_hex(24)}"

@router.get("", response_class=HTMLResponse)
async def get_onboarding_page(request: Request):
    """Render the onboarding page."""
    return templates.TemplateResponse("onboarding.html", {"request": request})

@router.post("/initiate-shopify")
async def initiate_shopify_connection(body: ShopifyConnectRequest):
    """
    Handle Shopify connection request from UI.
    Creates tenant if needed -> returns OAuth redirect URL.
    """
    shop_url = body.shopify_store_url.strip()
    if not shop_url:
        raise HTTPException(status_code=400, detail="Store URL is required")

    # Normalize domain
    if "://" in shop_url:
        shop_url = shop_url.split("://")[1]
    shop_url = shop_url.split("/")[0]

    conn = psycopg2.connect(get_db_url())
    tenant_id = None
    
    try:
        with conn.cursor() as cur:
            # Always create a new tenant — never reuse an existing one
            # by shop URL, as that would leak data between users.
            logger.info(f"Creating new tenant for {shop_url}")
            api_key = _generate_api_key()
            cur.execute(
                """
                INSERT INTO public.tenants (name, shopify_store_url, api_key)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (shop_url, shop_url, api_key)
            )
            tenant_id = cur.fetchone()[0]

            # Create schema and tables
            create_tenant_schema_and_tables(conn, tenant_id)
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to create tenant: {e}")
        raise HTTPException(status_code=500, detail="Failed to initialize tenant")
    finally:
        conn.close()

    # Construct the auth initiation URL
    # We point to our existing auth flow endpoint
    redirect_url = f"{settings.app_base_url}/api/auth/shopify/initiate/{tenant_id}?shop={shop_url}"
    
    return {"redirect_url": redirect_url}
