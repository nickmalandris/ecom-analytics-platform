"""
Model Runner: Execute staging and mart SQL models in dependency order.

Creates materialized views in an analytics schema from raw Airbyte data.
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

# Staging models must run first (they read from raw schema)
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
    return os.getenv("DATABASE_URL", "postgresql://analytics_user:analytics_pass@localhost:5435/analytics")


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


def run_model(conn, sql_path: Path, raw_schema: str, analytics_schema: str) -> tuple[str, float]:
    """
    Execute a single SQL model file.

    Replaces placeholders:
      {raw_schema} -> the tenant's raw data schema (e.g., raw_tenant_1)
      {analytics_schema} -> the tenant's analytics schema (e.g., analytics_tenant_1)

    Returns (model_name, elapsed_seconds).
    """
    model_name = sql_path.stem
    sql = sql_path.read_text()

    # Replace schema placeholders
    sql = sql.replace("{raw_schema}", raw_schema)
    sql = sql.replace("{analytics_schema}", analytics_schema)

    t0 = time.time()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    elapsed = time.time() - t0

    return model_name, elapsed


def verify_models(conn, analytics_schema: str):
    """Print row counts for all materialized views in the analytics schema."""
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT matviewname
            FROM pg_matviews
            WHERE schemaname = '{analytics_schema}'
            ORDER BY matviewname
        """)
        views = cur.fetchall()

        if not views:
            print("  No materialized views found!")
            return

        print(f"\n{'View':<45} {'Rows':>10}")
        print(f"{'-'*45} {'-'*10}")

        for (view_name,) in views:
            cur.execute(f"SELECT COUNT(*) FROM {analytics_schema}.{view_name}")
            count = cur.fetchone()[0]
            print(f"  {view_name:<43} {count:>10,}")


def main():
    args = parse_args()
    db_url = args.db_url or get_db_url()
    raw_schema = f"raw_tenant_{args.tenant_id}"
    analytics_schema = f"analytics_tenant_{args.tenant_id}"

    print(f"\nModel Runner Configuration:")
    print(f"  Database:         {db_url.split('@')[1] if '@' in db_url else db_url}")
    print(f"  Raw Schema:       {raw_schema}")
    print(f"  Analytics Schema: {analytics_schema}")
    print()

    conn = psycopg2.connect(db_url)

    try:
        # Create analytics schema
        with conn.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {analytics_schema}")
        conn.commit()
        print(f"  Ensured schema: {analytics_schema}")

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

            model_name, elapsed = run_model(conn, sql_path, raw_schema, analytics_schema)
            total_time += elapsed
            print(f"  OK  {model_name:<40} ({elapsed:.2f}s)")

        print(f"\n  Total model execution time: {total_time:.2f}s")

        # Verify
        print("\n" + "=" * 60)
        print("MODEL VERIFICATION")
        print("=" * 60)
        verify_models(conn, analytics_schema)
        print("=" * 60)

    finally:
        conn.close()

    print("\nDone! All models refreshed successfully.")


if __name__ == "__main__":
    main()
