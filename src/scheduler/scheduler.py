"""
APScheduler configuration for automated weekly reports.

Runs every Monday at 8:00 AM AEST (Sunday 21:00 UTC).
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from src.scheduler.jobs import run_all_tenant_reports

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def start_scheduler():
    """Start the background scheduler with the weekly report job."""
    if scheduler.running:
        logger.warning("Scheduler already running")
        return

    # Monday 8:00 AM AEST = Sunday 21:00 UTC
    # AEST is UTC+10 (no DST for simplicity; AEDT would be UTC+11)
    scheduler.add_job(
        run_all_tenant_reports,
        trigger=CronTrigger(
            day_of_week="sun",
            hour=21,
            minute=0,
            timezone="UTC",
        ),
        id="weekly_report",
        name="Weekly Analytics Report - All Tenants",
        replace_existing=True,
        misfire_grace_time=3600,  # 1 hour grace period
    )

    scheduler.start()
    logger.info("Scheduler started — weekly reports every Monday 8:00 AM AEST")


def stop_scheduler():
    """Gracefully shut down the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
