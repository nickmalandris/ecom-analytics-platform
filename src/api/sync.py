"""
Sync API endpoints for triggering Shopify data ingestion.
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.auth import require_admin, resolve_tenant

router = APIRouter(prefix="/sync", tags=["sync"])
logger = logging.getLogger(__name__)


class SyncRequest(BaseModel):
    mode: str = Field(
        default="incremental",
        description="Sync mode: 'full' (bulk operations) or 'incremental' (paginated)",
    )


class SyncResponse(BaseModel):
    status: str
    message: str
    details: dict | None = None


class SyncStatusResponse(BaseModel):
    tenant_id: int
    resources: list[dict]


@router.post("/shopify", response_model=SyncResponse)
def trigger_shopify_sync(
    body: SyncRequest,
    background_tasks: BackgroundTasks,
    tenant: dict = Depends(resolve_tenant),
):
    """
    Trigger a Shopify data sync for the current tenant.

    - mode=full: Uses Bulk Operations API (for initial load or full refresh)
    - mode=incremental: Uses paginated queries (for ongoing sync)

    Runs in background and returns immediately.
    """
    if tenant.get("is_admin"):
        raise HTTPException(
            status_code=400,
            detail="Use /sync/shopify/{tenant_id} for admin-triggered syncs",
        )

    tenant_id = tenant["id"]
    mode = body.mode.lower()
    if mode not in ("full", "incremental"):
        raise HTTPException(status_code=400, detail="mode must be 'full' or 'incremental'")

    logger.info(f"Shopify sync triggered: tenant={tenant_id} mode={mode}")

    from src.ingestion.shopify_sync import full_sync, incremental_sync
    sync_fn = full_sync if mode == "full" else incremental_sync
    background_tasks.add_task(sync_fn, tenant_id)

    return SyncResponse(
        status="triggered",
        message=f"Shopify {mode} sync started for tenant {tenant_id}. Running in background.",
    )


@router.post("/meta", response_model=SyncResponse)
def trigger_meta_sync(
    body: SyncRequest,
    background_tasks: BackgroundTasks,
    tenant: dict = Depends(resolve_tenant),
):
    """
    Trigger a Meta Ads data sync for the current tenant.

    - mode=full: Truncates and re-pulls all data (lifetime insights)
    - mode=incremental: Upserts entities and last 7 days of insights

    Runs in background and returns immediately.
    """
    if tenant.get("is_admin"):
        raise HTTPException(
            status_code=400,
            detail="Use /sync/meta/{tenant_id} for admin-triggered syncs",
        )

    tenant_id = tenant["id"]
    mode = body.mode.lower()
    if mode not in ("full", "incremental"):
        raise HTTPException(status_code=400, detail="mode must be 'full' or 'incremental'")

    logger.info(f"Meta sync triggered: tenant={tenant_id} mode={mode}")

    from src.ingestion.meta_sync import full_sync, incremental_sync
    sync_fn = full_sync if mode == "full" else incremental_sync
    background_tasks.add_task(sync_fn, tenant_id)

    return SyncResponse(
        status="triggered",
        message=f"Meta {mode} sync started for tenant {tenant_id}. Running in background.",
    )


@router.post("/shopify/{tenant_id}", response_model=SyncResponse)
def trigger_shopify_sync_admin(
    tenant_id: int,
    body: SyncRequest,
    background_tasks: BackgroundTasks,
    _admin: dict = Depends(require_admin),
):
    """Trigger a Shopify sync for a specific tenant (admin only)."""
    mode = body.mode.lower()
    if mode not in ("full", "incremental"):
        raise HTTPException(status_code=400, detail="mode must be 'full' or 'incremental'")

    logger.info(f"Admin-triggered Shopify sync: tenant={tenant_id} mode={mode}")

    from src.ingestion.shopify_sync import full_sync, incremental_sync
    sync_fn = full_sync if mode == "full" else incremental_sync
    background_tasks.add_task(sync_fn, tenant_id)

    return SyncResponse(
        status="triggered",
        message=f"Shopify {mode} sync started for tenant {tenant_id}. Running in background.",
    )


@router.post("/meta/{tenant_id}", response_model=SyncResponse)
def trigger_meta_sync_admin(
    tenant_id: int,
    body: SyncRequest,
    background_tasks: BackgroundTasks,
    _admin: dict = Depends(require_admin),
):
    """Trigger a Meta sync for a specific tenant (admin only)."""
    mode = body.mode.lower()
    if mode not in ("full", "incremental"):
        raise HTTPException(status_code=400, detail="mode must be 'full' or 'incremental'")

    logger.info(f"Admin-triggered Meta sync: tenant={tenant_id} mode={mode}")

    from src.ingestion.meta_sync import full_sync, incremental_sync
    sync_fn = full_sync if mode == "full" else incremental_sync
    background_tasks.add_task(sync_fn, tenant_id)

    return SyncResponse(
        status="triggered",
        message=f"Meta {mode} sync started for tenant {tenant_id}. Running in background.",
    )


@router.get("/status", response_model=SyncStatusResponse)
def get_sync_status(tenant: dict = Depends(resolve_tenant)):
    """Get the sync status for all resources for the current tenant."""
    import os
    import psycopg2
    from dotenv import load_dotenv
    from src.ingestion.sync_state import ensure_sync_state_table, get_sync_status as _get_status

    load_dotenv()
    tenant_id = tenant["id"] if not tenant.get("is_admin") else 0

    if tenant.get("is_admin"):
        raise HTTPException(status_code=400, detail="Use /sync/status/{tenant_id} for admin")

    db_url = os.getenv("DATABASE_URL", "postgresql://analytics_user:analytics_pass@localhost:5435/analytics")
    conn = psycopg2.connect(db_url)
    try:
        ensure_sync_state_table(conn)
        resources = _get_status(conn, tenant_id)
    finally:
        conn.close()

    return SyncStatusResponse(tenant_id=tenant_id, resources=resources)


@router.get("/status/{tenant_id}", response_model=SyncStatusResponse)
def get_sync_status_admin(
    tenant_id: int,
    _admin: dict = Depends(require_admin),
):
    """Get sync status for a specific tenant (admin only)."""
    import os
    import psycopg2
    from dotenv import load_dotenv
    from src.ingestion.sync_state import ensure_sync_state_table, get_sync_status as _get_status

    load_dotenv()
    db_url = os.getenv("DATABASE_URL", "postgresql://analytics_user:analytics_pass@localhost:5435/analytics")
    conn = psycopg2.connect(db_url)
    try:
        ensure_sync_state_table(conn)
        resources = _get_status(conn, tenant_id)
    finally:
        conn.close()

    return SyncStatusResponse(tenant_id=tenant_id, resources=resources)
