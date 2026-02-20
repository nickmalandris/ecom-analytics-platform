"""
Scheduler jobs for automated weekly report generation and delivery.

Uses APScheduler to run the report pipeline every Monday at 8:00 AM AEST.
"""

import logging
import os
from datetime import date, timedelta

import psycopg2
from dotenv import load_dotenv

from src.agent.agent import generate_report
from src.data.model_runner import get_db_url as get_db_url_from_runner
from src.email.sender import send_report_email_sync
from src.reports.builder import build_weekly_report

logger = logging.getLogger(__name__)


def get_tenant_info(db_url: str, tenant_id: int) -> dict | None:
    """Fetch tenant info from the database."""
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, email_recipients FROM public.tenants WHERE id = %s",
                (tenant_id,),
            )
            row = cur.fetchone()
            if row:
                return {
                    "id": row[0],
                    "name": row[1],
                    "email_recipients": row[2] or [],
                }
            return None
    finally:
        conn.close()


def run_weekly_report(tenant_id: int = 1) -> str | None:
    """
    Full pipeline: refresh models -> generate report -> build email -> send.

    Returns the report text if successful, None on failure.
    """
    load_dotenv()
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql://analytics_user:analytics_pass@localhost:5435/analytics",
    )

    logger.info(f"Starting weekly report for tenant {tenant_id}")

    # 1. Get tenant info
    tenant = get_tenant_info(db_url, tenant_id)
    if not tenant:
        logger.error(f"Tenant {tenant_id} not found")
        return None

    # 2. Refresh materialized views
    logger.info("Refreshing data models...")
    try:
        from src.data.model_runner import run_model, get_db_url
        from pathlib import Path
        import time

        PROJECT_ROOT = Path(__file__).parent.parent.parent
        SQL_DIR = PROJECT_ROOT / "sql"
        raw_schema = f"raw_tenant_{tenant_id}"
        analytics_schema = f"analytics_tenant_{tenant_id}"

        conn = psycopg2.connect(db_url)
        with conn.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {analytics_schema}")
        conn.commit()

        from src.data.model_runner import ALL_MODELS
        for model_path_str in ALL_MODELS:
            sql_path = SQL_DIR / model_path_str
            if sql_path.exists():
                run_model(conn, sql_path, raw_schema, analytics_schema)

        conn.close()
        logger.info("Data models refreshed")
    except Exception as e:
        logger.error(f"Failed to refresh models: {e}")
        # Continue anyway — stale data is better than no report
        pass

    # 3. Generate report via agent
    logger.info("Generating report via LLM agent...")
    report_end = date.today() - timedelta(days=1)  # Yesterday
    try:
        report_text = generate_report(
            tenant_id=tenant_id,
            report_end_date=report_end,
            db_url=db_url,
        )
    except Exception as e:
        logger.error(f"Agent failed to generate report: {e}")
        return None

    report_start = report_end - timedelta(days=6)
    logger.info(f"Report generated for {report_start} to {report_end}")

    # 4. Build HTML email
    html_body = build_weekly_report(
        report_text=report_text,
        tenant_name=tenant["name"],
        period_start=str(report_start),
        period_end=str(report_end),
    )

    # 5. Send email
    recipients = tenant["email_recipients"]
    if recipients:
        subject = f"Weekly Analytics Report | {tenant['name']} | {report_start} to {report_end}"
        sent = send_report_email_sync(
            to_addresses=recipients,
            subject=subject,
            html_body=html_body,
            plain_text=report_text,
        )
        if sent:
            logger.info(f"Report emailed to {recipients}")
        else:
            logger.warning("Email not sent (check SMTP config)")
    else:
        logger.warning(f"No email recipients configured for tenant {tenant_id}")

    return report_text


def run_all_tenant_reports():
    """Run weekly reports for all tenants."""
    load_dotenv()
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql://analytics_user:analytics_pass@localhost:5435/analytics",
    )

    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM public.tenants ORDER BY id")
            tenant_ids = [row[0] for row in cur.fetchall()]
    finally:
        conn.close()

    logger.info(f"Running reports for {len(tenant_ids)} tenants: {tenant_ids}")

    for tid in tenant_ids:
        try:
            run_weekly_report(tid)
        except Exception as e:
            logger.error(f"Failed to run report for tenant {tid}: {e}")
            continue
