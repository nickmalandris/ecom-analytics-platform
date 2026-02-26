"""
Database utilities and schema management.
"""

import os
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

# ─── Generic DB Utilities ────────────────────────────────

def get_db_url() -> str:
    """Get database URL from environment."""
    load_dotenv()
    return os.getenv("DATABASE_URL", "postgresql://analytics_user:analytics_pass@localhost:5432/analytics")


def fmt_counts(counts: dict[str, int], mode: str = "incremental") -> str:
    """Format upsert counts for logging."""
    if mode == "full":
        total = counts.get("inserted", 0) + counts.get("updated", 0) + counts.get("unchanged", 0)
        if total == 0:
            return "0"
        return f"{counts.get('inserted', 0)} inserted"

    parts = []
    if counts.get("inserted"):
        parts.append(f"{counts['inserted']} new")
    if counts.get("updated"):
        parts.append(f"{counts['updated']} updated")
    # Unchanged is usually hidden in incremental mode unless everything is unchanged?
    # Test 'test_unchanged_not_shown' says hidden.
    # But 'test_all_zeros' expects '0'.
    
    if not parts:
        return "0"
        
    return ", ".join(parts)


def fmt_summary(summary: dict, resource_keys: list[tuple[str, str]]) -> str:
    """Format sync summary for CLI output."""
    lines = [
        "",
        "=" * 60,
        f"SYNC SUMMARY: {summary.get('source', 'Shopify')} ({summary.get('mode', 'unknown')})",
        f"Tenant ID: {summary.get('tenant_id')}",
        "=" * 60,
    ]
    
    for key, label in resource_keys:
        if key in summary:
            counts = summary[key]
            lines.append(f"{label:<15} {fmt_counts(counts)}")
            
    lines.append("-" * 60)
    lines.append(f"Total Time:     {summary.get('elapsed_seconds', 0)}s")
    lines.append("=" * 60)
    lines.append("")
    return "\n".join(lines)


def upsert_rows(
    conn,
    schema: str,
    table: str,
    columns: list[str],
    rows: list[dict],
    conflict_keys: list[str] = ["id"],
) -> dict[str, int]:
    """
    Generic upsert: INSERT ... ON CONFLICT DO UPDATE ... WHERE <data changed>.

    The WHERE clause uses ROW() IS DISTINCT FROM to skip updates when data
    is identical, so unchanged rows are not touched at all.

    Uses RETURNING xmax to distinguish inserts (xmax=0) from real updates
    (xmax!=0). Rows that conflict but have no changes are not returned by
    RETURNING and are counted as unchanged.

    Returns {"inserted": N, "updated": M, "unchanged": K}.
    """
    if not rows:
        return {"inserted": 0, "updated": 0, "unchanged": 0}

    col_names = ", ".join(f'"{c}"' if c == "return" else c for c in columns)
    update_cols = [c for c in columns if c not in conflict_keys]

    def _col_ref(c: str, prefix: str = "") -> str:
        """Quote reserved words, optionally with table/alias prefix."""
        name = f'"{c}"' if c == "return" else c
        return f"{prefix}.{name}" if prefix else name

    if update_cols:
        update_set = ", ".join(
            f"{_col_ref(c)} = EXCLUDED.{_col_ref(c)}" for c in update_cols
        )
        # WHERE clause: only update if at least one column value actually changed.
        # ROW(existing cols) IS DISTINCT FROM ROW(incoming cols) handles NULLs correctly.
        existing_row = ", ".join(f"{schema}.{table}.{_col_ref(c)}" for c in update_cols)
        excluded_row = ", ".join(f"EXCLUDED.{_col_ref(c)}" for c in update_cols)
        where_clause = f"ROW({existing_row}) IS DISTINCT FROM ROW({excluded_row})"
        do_update = f"DO UPDATE SET {update_set} WHERE {where_clause}"
    else:
        do_update = "DO NOTHING"

    conflict_clause = ", ".join(f'"{k}"' if k == "return" else k for k in conflict_keys)

    sql = (
        f"INSERT INTO {schema}.{table} ({col_names}) VALUES %s "
        f"ON CONFLICT ({conflict_clause}) {do_update} "
        f"RETURNING (xmax = 0) AS is_insert"
    )

    batch = []
    for row in rows:
        values = []
        for col in columns:
            val = row.get(col)
            # Convert dicts/lists to Json wrapper for JSONB columns if needed
            if isinstance(val, (dict, list)):
                values.append(psycopg2.extras.Json(val))
            else:
                values.append(val)
        batch.append(tuple(values))

    inserted = 0
    updated = 0
    
    with conn.cursor() as cur:
        results = psycopg2.extras.execute_values(cur, sql, batch, page_size=500, fetch=True)
        for (is_insert,) in results:
            if is_insert:
                inserted += 1
            else:
                updated += 1
                
    return {
        "inserted": inserted,
        "updated": updated,
        "unchanged": len(rows) - inserted - updated,
    }


# ─── DDL Constants (extracted from seed.py) ──────────────────

SHOPIFY_PRODUCTS_DDL = """
CREATE TABLE IF NOT EXISTS {schema}.products (
    id BIGINT PRIMARY KEY,
    title TEXT,
    body_html TEXT,
    vendor TEXT,
    product_type TEXT,
    handle TEXT,
    status TEXT,
    tags TEXT,
    template_suffix TEXT,
    published_at TIMESTAMPTZ,
    published_scope TEXT,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    shop_url TEXT,
    admin_graphql_api_id TEXT,
    variants JSONB,
    options JSONB,
    image JSONB,
    images JSONB,
    total_inventory INT,
    total_variants INT
);
"""

SHOPIFY_PRODUCT_VARIANTS_DDL = """
CREATE TABLE IF NOT EXISTS {schema}.product_variants (
    id BIGINT PRIMARY KEY,
    product_id BIGINT,
    title TEXT,
    price TEXT,
    compare_at_price TEXT,
    sku TEXT,
    barcode TEXT,
    position INT,
    option1 TEXT,
    option2 TEXT,
    option3 TEXT,
    grams INT,
    weight NUMERIC,
    weight_unit TEXT,
    taxable BOOLEAN,
    tax_code TEXT,
    inventory_item_id BIGINT,
    inventory_quantity INT,
    old_inventory_quantity INT,
    inventory_policy TEXT,
    requires_shipping BOOLEAN,
    image_id BIGINT,
    image_src TEXT,
    available_for_sale BOOLEAN,
    display_name TEXT,
    admin_graphql_api_id TEXT,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    shop_url TEXT
);
"""

SHOPIFY_CUSTOMERS_DDL = """
CREATE TABLE IF NOT EXISTS {schema}.customers (
    id BIGINT PRIMARY KEY,
    email TEXT,
    first_name TEXT,
    last_name TEXT,
    phone TEXT,
    state TEXT,
    tags TEXT,
    currency TEXT,
    note TEXT,
    verified_email BOOLEAN,
    tax_exempt BOOLEAN,
    tax_exemptions TEXT,
    accepts_marketing BOOLEAN,
    accepts_marketing_updated_at TIMESTAMPTZ,
    marketing_opt_in_level TEXT,
    orders_count INT,
    total_spent TEXT,
    last_order_id BIGINT,
    last_order_name TEXT,
    admin_graphql_api_id TEXT,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    shop_url TEXT,
    default_address JSONB,
    addresses JSONB,
    email_marketing_consent JSONB,
    sms_marketing_consent JSONB
);
"""

SHOPIFY_ORDERS_DDL = """
CREATE TABLE IF NOT EXISTS {schema}.orders (
    id BIGINT PRIMARY KEY,
    admin_graphql_api_id TEXT,
    app_id BIGINT,
    browser_ip TEXT,
    buyer_accepts_marketing BOOLEAN,
    cancel_reason TEXT,
    cancelled_at TIMESTAMPTZ,
    cart_token TEXT,
    checkout_id BIGINT,
    checkout_token TEXT,
    closed_at TIMESTAMPTZ,
    confirmed BOOLEAN,
    confirmation_number TEXT,
    contact_email TEXT,
    created_at TIMESTAMPTZ,
    currency TEXT,
    current_subtotal_price TEXT,
    current_subtotal_price_set JSONB,
    current_total_discounts TEXT,
    current_total_discounts_set JSONB,
    current_total_price TEXT,
    current_total_price_set JSONB,
    current_total_tax TEXT,
    current_total_tax_set JSONB,
    customer_locale TEXT,
    discount_applications JSONB,
    discount_codes JSONB,
    email TEXT,
    financial_status TEXT,
    fulfillment_status TEXT,
    landing_site TEXT,
    name TEXT,
    note TEXT,
    note_attributes JSONB,
    number INT,
    order_number INT,
    order_status_url TEXT,
    payment_gateway_names JSONB,
    phone TEXT,
    presentment_currency TEXT,
    processed_at TIMESTAMPTZ,
    source_name TEXT,
    subtotal_price TEXT,
    subtotal_price_set JSONB,
    tags TEXT,
    tax_exempt BOOLEAN,
    tax_lines JSONB,
    taxes_included BOOLEAN,
    test BOOLEAN,
    token TEXT,
    total_discounts TEXT,
    total_discounts_set JSONB,
    total_line_items_price TEXT,
    total_line_items_price_set JSONB,
    total_outstanding TEXT,
    total_price TEXT,
    total_price_set JSONB,
    total_price_usd TEXT,
    total_shipping_price_set JSONB,
    total_tax TEXT,
    total_tax_set JSONB,
    total_tip_received TEXT,
    total_weight INT,
    updated_at TIMESTAMPTZ,
    customer JSONB,
    billing_address JSONB,
    shipping_address JSONB,
    shipping_lines JSONB,
    line_items JSONB,
    fulfillments JSONB,
    refunds JSONB,
    shop_url TEXT
);
"""

SHOPIFY_ORDER_REFUNDS_DDL = """
CREATE TABLE IF NOT EXISTS {schema}.order_refunds (
    id BIGINT PRIMARY KEY,
    order_id BIGINT,
    admin_graphql_api_id TEXT,
    created_at TIMESTAMPTZ,
    processed_at TIMESTAMPTZ,
    note TEXT,
    restock BOOLEAN,
    user_id BIGINT,
    duties TEXT,
    shop_url TEXT,
    return JSONB,
    total_duties_set JSONB,
    order_adjustments JSONB,
    refund_line_items JSONB,
    transactions JSONB
);
"""

META_CAMPAIGNS_DDL = """
CREATE TABLE IF NOT EXISTS {schema}.campaigns (
    id VARCHAR(255) PRIMARY KEY,
    account_id VARCHAR(255),
    name TEXT,
    status TEXT,
    effective_status TEXT,
    configured_status TEXT,
    objective TEXT,
    buying_type TEXT,
    bid_strategy TEXT,
    daily_budget TEXT,
    lifetime_budget TEXT,
    budget_remaining TEXT,
    spend_cap TEXT,
    start_time TIMESTAMPTZ,
    stop_time TIMESTAMPTZ,
    created_time TIMESTAMPTZ,
    updated_time TIMESTAMPTZ,
    special_ad_category TEXT,
    special_ad_category_country JSONB,
    adlabels JSONB,
    issues_info JSONB
);
"""

META_AD_SETS_DDL = """
CREATE TABLE IF NOT EXISTS {schema}.ad_sets (
    id VARCHAR(255) PRIMARY KEY,
    account_id VARCHAR(255),
    campaign_id VARCHAR(255),
    name TEXT,
    effective_status TEXT,
    daily_budget TEXT,
    lifetime_budget TEXT,
    budget_remaining TEXT,
    bid_strategy TEXT,
    bid_amount TEXT,
    bid_constraints JSONB,
    bid_info JSONB,
    start_time TIMESTAMPTZ,
    end_time TIMESTAMPTZ,
    created_time TIMESTAMPTZ,
    updated_time TIMESTAMPTZ,
    targeting JSONB,
    promoted_object JSONB,
    adlabels JSONB,
    learning_stage_info JSONB
);
"""

META_ADS_DDL = """
CREATE TABLE IF NOT EXISTS {schema}.ads (
    id VARCHAR(255) PRIMARY KEY,
    account_id VARCHAR(255),
    campaign_id VARCHAR(255),
    adset_id VARCHAR(255),
    name TEXT,
    status TEXT,
    effective_status TEXT,
    bid_type TEXT,
    bid_amount INT,
    bid_info JSONB,
    creative JSONB,
    created_time TIMESTAMPTZ,
    updated_time TIMESTAMPTZ,
    last_updated_by_app_id TEXT,
    source_ad_id TEXT,
    targeting JSONB,
    tracking_specs JSONB,
    conversion_specs JSONB,
    adlabels JSONB,
    recommendations JSONB
);
"""

META_ADS_INSIGHTS_DDL = """
CREATE TABLE IF NOT EXISTS {schema}.ads_insights (
    date_start DATE,
    date_stop DATE,
    account_id VARCHAR(255),
    account_name TEXT,
    account_currency TEXT,
    campaign_id VARCHAR(255),
    campaign_name TEXT,
    adset_id VARCHAR(255),
    adset_name TEXT,
    ad_id VARCHAR(255),
    ad_name TEXT,
    objective TEXT,
    optimization_goal TEXT,
    buying_type TEXT,
    attribution_setting TEXT,
    impressions BIGINT,
    clicks BIGINT,
    spend TEXT,
    reach BIGINT,
    frequency NUMERIC,
    cpc TEXT,
    cpm TEXT,
    cpp TEXT,
    ctr TEXT,
    unique_clicks BIGINT,
    unique_ctr TEXT,
    cost_per_unique_click TEXT,
    inline_link_clicks BIGINT,
    inline_link_click_ctr TEXT,
    inline_post_engagement BIGINT,
    cost_per_inline_link_click TEXT,
    cost_per_inline_post_engagement TEXT,
    social_spend TEXT,
    quality_ranking TEXT,
    engagement_rate_ranking TEXT,
    conversion_rate_ranking TEXT,
    actions JSONB,
    action_values JSONB,
    conversions JSONB,
    conversion_values JSONB,
    cost_per_action_type JSONB,
    cost_per_conversion JSONB,
    purchase_roas JSONB,
    website_purchase_roas JSONB,
    outbound_clicks JSONB,
    created_time TEXT,
    updated_time TEXT,
    PRIMARY KEY (date_start, account_id, ad_id)
);
"""

def create_tenant_schema_and_tables(conn, tenant_id: int):
    """
    Fully initialize a new tenant's database schema using Alembic.
    """
    schema = f"tenant_{tenant_id}"
    
    with conn.cursor() as cur:
        # Create Schema
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    conn.commit()

    # Run Alembic migrations for this specific schema
    import subprocess
    import sys
    from pathlib import Path

    project_root = Path(__file__).resolve().parent.parent.parent
    
    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "alembic.ini",
                "-n",
                "alembic_tenants",
                "-x",
                f"tenant_schema={schema}",
                "upgrade",
                "head",
            ],
            cwd=project_root,
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"Alembic migration failed for tenant {tenant_id}:")
        print(e.stderr.decode())
        raise
