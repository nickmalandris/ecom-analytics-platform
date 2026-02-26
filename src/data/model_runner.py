"""
Model Runner: Execute staging and mart SQL models in dependency order.

Creates materialized views from raw data within the tenant's single schema.
Supports per-tenant execution and full refresh.

Usage:
    uv run python -m src.data.model_runner --tenant-id 1
    uv run python -m src.data.model_runner --tenant-id 1 --models mart_daily_revenue
"""

import argparse
import os
import sys
import time
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

# Project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
SQL_DIR = PROJECT_ROOT / "sql"


# ──────────────────────────────────────────────
# Model execution order (respects dependencies)
# ──────────────────────────────────────────────

# Staging models must run first (they read from raw tables)
STAGING_MODELS = [
    "staging/stg_shopify_orders.sql",       # Also creates stg_shopify_order_lines
    "staging/stg_shopify_refunds.sql",
    "staging/stg_shopify_customers.sql",
    "staging/stg_shopify_products.sql",
    "staging/stg_meta_ad_insights.sql",
    "staging/stg_meta_campaigns.sql",       # Creates campaigns, ad_sets, ads views
]

# Mart models depend on staging views
MART_MODELS = [
    "marts/mart_daily_revenue.sql",         # Depends on stg_shopify_orders
    "marts/mart_daily_orders.sql",          # Depends on stg_shopify_orders, stg_shopify_refunds
    "marts/mart_daily_ad_performance.sql",  # Depends on stg_meta_ad_insights
    "marts/mart_daily_blended_performance.sql",  # Depends on stg_shopify_orders, stg_meta_ad_insights, stg_shopify_refunds
    "marts/mart_product_performance.sql",   # Depends on stg_shopify_order_lines, stg_shopify_refunds
    "marts/mart_customer_cohorts.sql",      # Depends on stg_shopify_orders
    "marts/mart_customer_ltv.sql",          # Depends on stg_shopify_orders
]

ALL_MODELS = STAGING_MODELS + MART_MODELS


def parse_args():
    parser = argparse.ArgumentParser(description="Run SQL data models")
    parser.add_argument("--db-url", type=str, default=None, help="PostgreSQL URL")
    parser.add_argument("--tenant-id", type=int, default=1, help="Tenant ID")
    parser.add_argument(
        "--models",
        type=str,
        nargs="*",
        default=None,
        help="Specific model names to run (e.g., mart_daily_revenue). Runs all if not specified.",
    )
    parser.add_argument(
        "--staging-only",
        action="store_true",
        help="Only run staging models",
    )
    parser.add_argument(
        "--marts-only",
        action="store_true",
        help="Only run mart models (assumes staging is already built)",
    )
    return parser.parse_args()


def get_db_url():
    load_dotenv(PROJECT_ROOT / ".env")
    return os.getenv("DATABASE_URL")


def get_models_to_run(args) -> list[str]:
    """Determine which models to run based on args."""
    if args.models:
        # Match model names to file paths
        matched = []
        for model_name in args.models:
            found = False
            for model_path in ALL_MODELS:
                if model_name in model_path:
                    matched.append(model_path)
                    found = True
                    break
            if not found:
                print(f"  WARNING: Model '{model_name}' not found, skipping")
        return matched
    elif args.staging_only:
        return STAGING_MODELS
    elif args.marts_only:
        return MART_MODELS
    else:
        return ALL_MODELS


def run_model(conn, sql_path: Path, schema: str) -> tuple[str, float]:
    """
    Execute a single SQL model file.

    Replaces the {schema} placeholder with the tenant's schema name
    (e.g., tenant_1).

    Returns (model_name, elapsed_seconds).
    """
    model_name = sql_path.stem
    sql = sql_path.read_text()

    # Replace schema placeholder
    sql = sql.replace("{schema}", schema)

    t0 = time.time()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    elapsed = time.time() - t0

    return model_name, elapsed


def refresh_models(tenant_id: int, db_url: str | None = None) -> dict:
    """
    Programmatic entry point: refresh all staging + mart views for a tenant.

    Called automatically after a data sync completes so the dashboard
    always reflects the latest raw data.

    Returns {"models_run": N, "elapsed_seconds": X}.
    """
    import logging
    _logger = logging.getLogger(__name__)

    if db_url is None:
        db_url = get_db_url()

    schema = f"tenant_{tenant_id}"
    conn = psycopg2.connect(db_url)
    try:
        total_time = 0.0
        count = 0
        for model_path_str in ALL_MODELS:
            sql_path = SQL_DIR / model_path_str
            if not sql_path.exists():
                _logger.warning("Model file not found: %s", sql_path)
                continue
            try:
                model_name, elapsed = run_model(conn, sql_path, schema)
                total_time += elapsed
                count += 1
                _logger.info("Refreshed %s (%.2fs)", model_name, elapsed)
            except Exception as e:
                # Log but continue — some models may fail if upstream data
                # is missing (e.g., Meta staging when only Shopify is connected)
                conn.rollback()
                _logger.warning("Model %s failed: %s", sql_path.stem, e)

        _logger.info(
            "Model refresh complete for tenant %s: %d models in %.2fs",
            tenant_id, count, total_time,
        )
        return {"models_run": count, "elapsed_seconds": round(total_time, 2)}
    finally:
        conn.close()


def verify_models(conn, schema: str):
    """Print row counts for all materialized views in the tenant schema."""
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT matviewname
            FROM pg_matviews
            WHERE schemaname = '{schema}'
            ORDER BY matviewname
        """)
        views = cur.fetchall()

        if not views:
            print("  No materialized views found!")
            return

        print(f"\n{'View':<45} {'Rows':>10}")
        print(f"{'-'*45} {'-'*10}")

        for (view_name,) in views:
            cur.execute(f"SELECT COUNT(*) FROM {schema}.{view_name}")
            count = cur.fetchone()[0]
            print(f"  {view_name:<43} {count:>10,}")


def main():
    args = parse_args()
    db_url = args.db_url or get_db_url()
    schema = f"tenant_{args.tenant_id}"

    print(f"\nModel Runner Configuration:")
    print(f"  Database:  {db_url.split('@')[1] if '@' in db_url else db_url}")
    print(f"  Schema:    {schema}")
    print()

    conn = psycopg2.connect(db_url)

    try:
        # Ensure schema exists
        with conn.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        conn.commit()
        print(f"  Ensured schema: {schema}")

        # Determine models to run
        models = get_models_to_run(args)
        print(f"  Models to run: {len(models)}")
        print()

        # Execute models in order
        total_time = 0
        for model_path_str in models:
            sql_path = SQL_DIR / model_path_str
            if not sql_path.exists():
                print(f"  ERROR: {sql_path} not found, skipping")
                continue

            model_name, elapsed = run_model(conn, sql_path, schema)
            total_time += elapsed
            print(f"  OK  {model_name:<40} ({elapsed:.2f}s)")

        print(f"\n  Total model execution time: {total_time:.2f}s")

        # Verify
        print("\n" + "=" * 60)
        print("MODEL VERIFICATION")
        print("=" * 60)
        verify_models(conn, schema)
        print("=" * 60)

    finally:
        conn.close()

    print("\nDone! All models refreshed successfully.")


if __name__ == "__main__":
    main()
