"""
Report API endpoints.

Trigger on-demand report generation and view report results.
"""

import logging
import os
from datetime import date, timedelta
from threading import Thread

from dotenv import load_dotenv
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from src.api.auth import require_admin, resolve_tenant
from src.api.schemas import ReportRequest, ReportResponse, ReportStatusResponse

router = APIRouter(prefix="/reports", tags=["reports"])
logger = logging.getLogger(__name__)

load_dotenv()


def _get_db_url() -> str:
    return os.getenv("DATABASE_URL")


@router.post("/generate", response_model=ReportResponse)
def generate_report_endpoint(
    body: ReportRequest,
    tenant: dict = Depends(resolve_tenant),
):
    """
    Generate a weekly analytics report on demand (synchronous).

    Uses the tenant identified by the API key. Returns the full report
    including both plain text and HTML versions.
    """
    if tenant.get("is_admin"):
        raise HTTPException(
            status_code=400,
            detail="Use /reports/generate/{tenant_id} for admin-triggered reports",
        )

    tenant_id = tenant["id"]
    end_date = date.fromisoformat(body.end_date) if body.end_date else date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=6)

    logger.info(f"On-demand report requested for tenant {tenant_id}: {start_date} to {end_date}")

    try:
        from src.agent.agent import generate_report
        from src.reports.builder import build_weekly_report

        report_text = generate_report(
            tenant_id=tenant_id,
            report_end_date=end_date,
            db_url=_get_db_url(),
        )

        html_report = build_weekly_report(
            report_text=report_text,
            tenant_name=tenant["name"],
            period_start=str(start_date),
            period_end=str(end_date),
        )

        return ReportResponse(
            tenant_id=tenant_id,
            period_start=str(start_date),
            period_end=str(end_date),
            report_text=report_text,
            html_report=html_report,
        )
    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Report generation failed: {e}")


@router.post("/generate/{tenant_id}", response_model=ReportResponse)
def generate_report_for_tenant(
    tenant_id: int,
    body: ReportRequest,
    _admin: dict = Depends(require_admin),
):
    """Generate a report for a specific tenant (admin only, synchronous)."""
    end_date = date.fromisoformat(body.end_date) if body.end_date else date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=6)

    # Look up tenant name
    import psycopg2
    conn = psycopg2.connect(_get_db_url())
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT name FROM public.tenants WHERE id = %s", (tenant_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Tenant not found")
            tenant_name = row[0]
    finally:
        conn.close()

    logger.info(f"Admin-triggered report for tenant {tenant_id}: {start_date} to {end_date}")

    try:
        from src.agent.agent import generate_report
        from src.reports.builder import build_weekly_report

        report_text = generate_report(
            tenant_id=tenant_id,
            report_end_date=end_date,
            db_url=_get_db_url(),
        )

        html_report = build_weekly_report(
            report_text=report_text,
            tenant_name=tenant_name,
            period_start=str(start_date),
            period_end=str(end_date),
        )

        return ReportResponse(
            tenant_id=tenant_id,
            period_start=str(start_date),
            period_end=str(end_date),
            report_text=report_text,
            html_report=html_report,
        )
    except Exception as e:
        logger.error(f"Report generation failed for tenant {tenant_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Report generation failed: {e}")


@router.post("/trigger-all", response_model=ReportStatusResponse)
def trigger_all_reports(
    background_tasks: BackgroundTasks,
    _admin: dict = Depends(require_admin),
):
    """
    Trigger weekly reports for all tenants (admin only, async background task).

    Returns immediately with a status message.
    """
    from src.scheduler.jobs import run_all_tenant_reports

    background_tasks.add_task(run_all_tenant_reports)

    return ReportStatusResponse(
        status="triggered",
        message="Weekly reports triggered for all tenants. Running in background.",
    )
