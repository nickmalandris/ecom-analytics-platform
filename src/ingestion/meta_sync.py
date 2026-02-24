"""
Meta Ads data sync orchestrator.

Two sync modes:
  - Full sync (--full): Pulls all campaigns, ad sets, ads, and lifetime insights.
    Truncates raw Meta tables before inserting.
  - Incremental sync (--incremental): Pulls all campaigns/ad sets/ads (small enough to refresh),
    and insights for the last 7 days (to capture attribution changes).
    Uses upsert for all operations.

Usage:
    uv run python -m src.ingestion.meta_sync --tenant-id 1 --full
    uv run python -m src.ingestion.meta_sync --tenant-id 1 --incremental
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone

import psycopg2
from dotenv import load_dotenv

from src.ingestion.db_utils import fmt_summary, get_db_url, upsert_rows
from src.ingestion.meta_client import MetaClient, MetaClientError
from src.ingestion.sync_state import (
    ensure_sync_state_table,
    mark_sync_completed,
    mark_sync_failed,
    mark_sync_started,
)

logger = logging.getLogger(__name__)

META_RESOURCE_KEYS = [
    ("campaigns", "Campaigns"),
    ("ad_sets", "Ad Sets"),
    ("ads", "Ads"),
    ("ads_insights", "Insights"),
]


# ─── DB helpers ──────────────────────────────────────────


def _upsert_campaigns(conn, schema: str, rows: list[dict]) -> dict[str, int]:
    """Upsert campaign rows."""
    if not rows:
        return {"inserted": 0, "updated": 0, "unchanged": 0}
    # Fields match MetaClient.CAMPAIGN_FIELDS
    columns = [
        "id", "account_id", "name", "status", "effective_status", "configured_status",
        "objective", "buying_type", "bid_strategy", "daily_budget", "lifetime_budget",
        "budget_remaining", "spend_cap", "start_time", "stop_time", "created_time",
        "updated_time", "special_ad_category", "special_ad_category_country",
        "adlabels", "issues_info",
    ]
    return upsert_rows(conn, schema, "campaigns", columns, rows, conflict_keys=["id"])


def _upsert_ad_sets(conn, schema: str, rows: list[dict]) -> dict[str, int]:
    """Upsert ad set rows."""
    if not rows:
        return {"inserted": 0, "updated": 0, "unchanged": 0}
    # Fields match MetaClient.AD_SET_FIELDS
    columns = [
        "id", "account_id", "campaign_id", "name", "effective_status", "daily_budget",
        "lifetime_budget", "budget_remaining", "bid_strategy", "bid_amount",
        "bid_constraints", "bid_info", "start_time", "end_time", "created_time",
        "updated_time", "targeting", "promoted_object", "adlabels", "learning_stage_info",
    ]
    return upsert_rows(conn, schema, "ad_sets", columns, rows, conflict_keys=["id"])


def _upsert_ads(conn, schema: str, rows: list[dict]) -> dict[str, int]:
    """Upsert ad rows."""
    if not rows:
        return {"inserted": 0, "updated": 0, "unchanged": 0}
    # Fields match MetaClient.AD_FIELDS
    columns = [
        "id", "account_id", "campaign_id", "adset_id", "name", "status", "effective_status",
        "bid_type", "bid_amount", "bid_info", "creative", "created_time", "updated_time",
        "last_updated_by_app_id", "source_ad_id", "targeting", "tracking_specs",
        "conversion_specs", "adlabels", "recommendations",
    ]
    return upsert_rows(conn, schema, "ads", columns, rows, conflict_keys=["id"])


def _upsert_insights(conn, schema: str, rows: list[dict]) -> dict[str, int]:
    """Upsert ads insights rows."""
    if not rows:
        return {"inserted": 0, "updated": 0, "unchanged": 0}
    # Fields match MetaClient.INSIGHT_FIELDS
    columns = [
        "date_start", "date_stop", "account_id", "account_name", "account_currency",
        "campaign_id", "campaign_name", "adset_id", "adset_name", "ad_id", "ad_name",
        "objective", "optimization_goal", "buying_type", "attribution_setting",
        "impressions", "clicks", "spend", "reach", "frequency", "cpc", "cpm", "cpp", "ctr",
        "unique_clicks", "unique_ctr", "cost_per_unique_click", "inline_link_clicks",
        "inline_link_click_ctr", "inline_post_engagement",
        "cost_per_inline_link_click", "cost_per_inline_post_engagement",
        "social_spend", "quality_ranking", "engagement_rate_ranking",
        "conversion_rate_ranking", "actions", "action_values", "conversions",
        "conversion_values", "cost_per_action_type", "cost_per_conversion",
        "purchase_roas", "website_purchase_roas", "outbound_clicks",
    ]
    # Composite PK: (date_start, account_id, ad_id)
    return upsert_rows(
        conn,
        schema,
        "ads_insights",
        columns,
        rows,
        conflict_keys=["date_start", "account_id", "ad_id"],
    )


# ─── Sync Logic ──────────────────────────────────────────


def _sync_entities(
    client: MetaClient, conn, schema: str, tenant_id: int, summary: dict, start_time: datetime
):
    """Sync campaigns, ad sets, and ads (always full pull)."""
    
    # Campaigns
    mark_sync_started(conn, tenant_id, "campaigns")
    try:
        rows = []
        for page in client.get_campaigns():
            rows.extend(page)
        counts = _upsert_campaigns(conn, schema, rows)
        summary["campaigns"] = counts
        mark_sync_completed(conn, tenant_id, "campaigns", len(rows), start_time)
    except Exception as e:
        mark_sync_failed(conn, tenant_id, "campaigns", str(e))
        raise

    # Ad Sets
    mark_sync_started(conn, tenant_id, "ad_sets")
    try:
        rows = []
        for page in client.get_ad_sets():
            rows.extend(page)
        counts = _upsert_ad_sets(conn, schema, rows)
        summary["ad_sets"] = counts
        mark_sync_completed(conn, tenant_id, "ad_sets", len(rows), start_time)
    except Exception as e:
        mark_sync_failed(conn, tenant_id, "ad_sets", str(e))
        raise

    # Ads
    mark_sync_started(conn, tenant_id, "ads")
    try:
        rows = []
        for page in client.get_ads():
            rows.extend(page)
        counts = _upsert_ads(conn, schema, rows)
        summary["ads"] = counts
        mark_sync_completed(conn, tenant_id, "ads", len(rows), start_time)
    except Exception as e:
        mark_sync_failed(conn, tenant_id, "ads", str(e))
        raise


def _sync_insights(
    client: MetaClient,
    conn,
    schema: str,
    tenant_id: int,
    summary: dict,
    start_time: datetime,
    date_preset: str = "last_7d",
):
    """Sync ads insights."""
    mark_sync_started(conn, tenant_id, "ads_insights")
    try:
        rows = []
        for page in client.get_insights(date_preset=date_preset, level="ad"):
            rows.extend(page)
        counts = _upsert_insights(conn, schema, rows)
        summary["ads_insights"] = counts
        mark_sync_completed(conn, tenant_id, "ads_insights", len(rows), start_time)
    except Exception as e:
        mark_sync_failed(conn, tenant_id, "ads_insights", str(e))
        raise


def full_sync(tenant_id: int, db_url: str | None = None) -> dict:
    """
    Full sync: truncate tables and re-fetch everything (lifetime insights).
    """
    load_dotenv()
    db_url = db_url or get_db_url()
    conn = psycopg2.connect(db_url)
    schema = f"tenant_{tenant_id}"

    try:
        ensure_sync_state_table(conn)
        
        logger.info(f"Starting Meta full sync for tenant {tenant_id}")
        sync_start = datetime.now(timezone.utc)
        summary = {"mode": "full", "tenant_id": tenant_id, "source": "Meta"}

        # Truncate raw tables for clean slate
        with conn.cursor() as cur:
            for table in ["ads_insights", "ads", "ad_sets", "campaigns"]:
                cur.execute(f"TRUNCATE TABLE {schema}.{table} CASCADE")
        conn.commit()
        logger.info(f"Truncated Meta tables in {schema}")

        with MetaClient(tenant_id=tenant_id, conn=conn) as client:
            _sync_entities(client, conn, schema, tenant_id, summary, sync_start)
            _sync_insights(client, conn, schema, tenant_id, summary, sync_start, date_preset="lifetime")

        elapsed = (datetime.now(timezone.utc) - sync_start).total_seconds()
        summary["elapsed_seconds"] = round(elapsed, 1)
        return summary

    finally:
        conn.close()


def incremental_sync(tenant_id: int, db_url: str | None = None) -> dict:
    """
    Incremental sync: re-fetch entities, fetch insights for last 7 days.
    """
    load_dotenv()
    db_url = db_url or get_db_url()
    conn = psycopg2.connect(db_url)
    schema = f"tenant_{tenant_id}"

    try:
        ensure_sync_state_table(conn)

        logger.info(f"Starting Meta incremental sync for tenant {tenant_id}")
        sync_start = datetime.now(timezone.utc)
        summary = {"mode": "incremental", "tenant_id": tenant_id, "source": "Meta"}

        with MetaClient(tenant_id=tenant_id, conn=conn) as client:
            _sync_entities(client, conn, schema, tenant_id, summary, sync_start)
            # 7-day lookback for attribution window changes
            _sync_insights(client, conn, schema, tenant_id, summary, sync_start, date_preset="last_7d")

        elapsed = (datetime.now(timezone.utc) - sync_start).total_seconds()
        summary["elapsed_seconds"] = round(elapsed, 1)
        return summary

    finally:
        conn.close()


# ─── CLI ─────────────────────────────────────────────────


def parse_args():
    parser = argparse.ArgumentParser(description="Sync Meta Ads data via Marketing API")
    parser.add_argument("--tenant-id", type=int, default=1, help="Tenant ID")
    parser.add_argument("--db-url", type=str, default=None, help="Database URL")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--full", action="store_true", help="Full sync (truncate + lifetime)")
    mode.add_argument("--incremental", action="store_true", help="Incremental sync (last 7 days)")
    return parser.parse_args()


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    args = parse_args()
    load_dotenv()
    db_url = args.db_url or get_db_url()

    try:
        if args.full:
            result = full_sync(args.tenant_id, db_url)
        else:
            result = incremental_sync(args.tenant_id, db_url)

        print(fmt_summary(result, META_RESOURCE_KEYS))
    except MetaClientError as e:
        print(f"\nSync failed: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}", file=sys.stderr)
        logger.exception("Sync failed with unexpected error")
        sys.exit(1)


if __name__ == "__main__":
    main()
