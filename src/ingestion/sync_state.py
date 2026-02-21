"""
Sync state tracking for incremental data ingestion.

Maintains a `public.sync_state` table that tracks per-tenant, per-resource
sync cursors, status, and metadata.
"""

import logging
from datetime import datetime, timezone

import psycopg2

logger = logging.getLogger(__name__)

SYNC_STATE_DDL = """
CREATE TABLE IF NOT EXISTS public.sync_state (
    id SERIAL PRIMARY KEY,
    tenant_id INT NOT NULL,
    resource TEXT NOT NULL,
    last_synced_at TIMESTAMPTZ,
    sync_status TEXT DEFAULT 'idle',
    records_synced INT DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    UNIQUE(tenant_id, resource)
);
"""

RESOURCES = ["products", "customers", "orders", "order_refunds"]


def ensure_sync_state_table(conn: psycopg2.extensions.connection) -> None:
    """Create the sync_state table if it doesn't exist."""
    with conn.cursor() as cur:
        cur.execute(SYNC_STATE_DDL)
    conn.commit()


def get_last_sync(
    conn: psycopg2.extensions.connection,
    tenant_id: int,
    resource: str,
) -> datetime | None:
    """
    Get the last successful sync timestamp for a resource.

    Returns None if no sync has ever completed (triggers full sync).
    """
    with conn.cursor() as cur:
        cur.execute(
            """SELECT last_synced_at FROM public.sync_state
               WHERE tenant_id = %s AND resource = %s AND sync_status = 'completed'""",
            (tenant_id, resource),
        )
        row = cur.fetchone()
    return row[0] if row else None


def is_sync_running(
    conn: psycopg2.extensions.connection,
    tenant_id: int,
    resource: str,
) -> bool:
    """Check if a sync is currently running for this resource."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT sync_status FROM public.sync_state
               WHERE tenant_id = %s AND resource = %s""",
            (tenant_id, resource),
        )
        row = cur.fetchone()
    return row is not None and row[0] == "running"


def mark_sync_started(
    conn: psycopg2.extensions.connection,
    tenant_id: int,
    resource: str,
) -> None:
    """Mark a resource sync as started."""
    now = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO public.sync_state (tenant_id, resource, sync_status, started_at, records_synced, error_message)
               VALUES (%s, %s, 'running', %s, 0, NULL)
               ON CONFLICT (tenant_id, resource) DO UPDATE SET
                   sync_status = 'running',
                   started_at = %s,
                   records_synced = 0,
                   error_message = NULL""",
            (tenant_id, resource, now, now),
        )
    conn.commit()
    logger.info(f"Sync started: tenant={tenant_id} resource={resource}")


def mark_sync_completed(
    conn: psycopg2.extensions.connection,
    tenant_id: int,
    resource: str,
    records_synced: int,
    sync_timestamp: datetime | None = None,
) -> None:
    """Mark a resource sync as completed successfully."""
    now = datetime.now(timezone.utc)
    ts = sync_timestamp or now
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE public.sync_state
               SET sync_status = 'completed',
                   last_synced_at = %s,
                   completed_at = %s,
                   records_synced = %s,
                   error_message = NULL
               WHERE tenant_id = %s AND resource = %s""",
            (ts, now, records_synced, tenant_id, resource),
        )
    conn.commit()
    logger.info(
        f"Sync completed: tenant={tenant_id} resource={resource} records={records_synced}"
    )


def mark_sync_failed(
    conn: psycopg2.extensions.connection,
    tenant_id: int,
    resource: str,
    error_message: str,
) -> None:
    """Mark a resource sync as failed."""
    # Rollback any active transaction so we can write the error state
    conn.rollback()
    
    now = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE public.sync_state
               SET sync_status = 'failed',
                   completed_at = %s,
                   error_message = %s
               WHERE tenant_id = %s AND resource = %s""",
            (now, error_message[:2000], tenant_id, resource),
        )
    conn.commit()
    logger.error(
        f"Sync failed: tenant={tenant_id} resource={resource} error={error_message[:200]}"
    )


def get_sync_status(
    conn: psycopg2.extensions.connection,
    tenant_id: int,
) -> list[dict]:
    """Get sync status for all resources for a tenant."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT resource, sync_status, last_synced_at, records_synced,
                      error_message, started_at, completed_at
               FROM public.sync_state
               WHERE tenant_id = %s
               ORDER BY resource""",
            (tenant_id,),
        )
        rows = cur.fetchall()

    return [
        {
            "resource": r[0],
            "status": r[1],
            "last_synced_at": r[2].isoformat() if r[2] else None,
            "records_synced": r[3],
            "error": r[4],
            "started_at": r[5].isoformat() if r[5] else None,
            "completed_at": r[6].isoformat() if r[6] else None,
        }
        for r in rows
    ]
