"""
Seed script: Generate realistic Shopify + Meta Ads data into PostgreSQL.

Usage:
    uv run python -m scripts.seed --clean
    uv run python -m scripts.seed --tenant-id 1 --days 90
"""

import argparse
import json
import os
import sys
import time
from datetime import date, timedelta

import psycopg2
import psycopg2.extras
from psycopg2.extras import Json
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.generators.shopify import generate_products, generate_customers, generate_orders
from scripts.generators.meta_ads import generate_campaigns, generate_ad_sets, generate_ads, generate_ads_insights


def parse_args():
    parser = argparse.ArgumentParser(description="Seed analytics database with test data")
    parser.add_argument("--db-url", type=str, default=None, help="PostgreSQL connection URL (reads from .env if not set)")
    parser.add_argument("--tenant-id", type=int, default=1, help="Tenant ID to seed (default: 1)")
    parser.add_argument("--days", type=int, default=90, help="Number of days of data to generate (default: 90)")
    parser.add_argument("--clean", action="store_true", help="Drop and recreate schemas before seeding")
    return parser.parse_args()


# ──────────────────────────────────────────────
# DDL: Table definitions
# ──────────────────────────────────────────────

TENANT_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS public.tenants (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    shopify_store_url VARCHAR(255),
    meta_account_id VARCHAR(255),
    api_key VARCHAR(255) NOT NULL,
    email_recipients TEXT[],
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
"""

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


def get_db_url():
    """Get database URL from environment."""
    load_dotenv()
    return os.getenv("DATABASE_URL", "postgresql://analytics_user:analytics_pass@localhost:5432/analytics")


def connect(db_url: str):
    """Create a psycopg2 connection."""
    return psycopg2.connect(db_url)


def setup_schema(conn, schema: str, clean: bool = False):
    """Create (or recreate) the raw data schema."""
    with conn.cursor() as cur:
        if clean:
            cur.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE;")
            print(f"  Dropped schema: {schema}")
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema};")
        print(f"  Created schema: {schema}")
    conn.commit()


def create_tables(conn, schema: str):
    """Create all tables in the given schema."""
    ddl_statements = [
        ("products", SHOPIFY_PRODUCTS_DDL),
        ("product_variants", SHOPIFY_PRODUCT_VARIANTS_DDL),
        ("customers", SHOPIFY_CUSTOMERS_DDL),
        ("orders", SHOPIFY_ORDERS_DDL),
        ("order_refunds", SHOPIFY_ORDER_REFUNDS_DDL),
        ("campaigns", META_CAMPAIGNS_DDL),
        ("ad_sets", META_AD_SETS_DDL),
        ("ads", META_ADS_DDL),
        ("ads_insights", META_ADS_INSIGHTS_DDL),
    ]

    with conn.cursor() as cur:
        for table_name, ddl in ddl_statements:
            cur.execute(ddl.format(schema=schema))
            print(f"  Created table: {schema}.{table_name}")
    conn.commit()


def create_tenant(conn, tenant_id: int):
    """Create the tenants table and insert a tenant."""
    with conn.cursor() as cur:
        cur.execute(TENANT_TABLE_DDL)
        cur.execute(
            """
            INSERT INTO public.tenants (id, name, shopify_store_url, meta_account_id, api_key, email_recipients)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                shopify_store_url = EXCLUDED.shopify_store_url,
                meta_account_id = EXCLUDED.meta_account_id,
                updated_at = NOW();
            """,
            (
                tenant_id,
                "Test Store AU",
                "https://test-store.myshopify.com",
                "act_1234567890",
                "sk_test_analytics_key_001",
                ["owner@teststore.com.au"],
            ),
        )
        print(f"  Created tenant: id={tenant_id}")
    conn.commit()


def bulk_insert(conn, schema: str, table: str, rows: list[dict], columns: list[str]):
    """Insert rows into a table using batch execute."""
    if not rows:
        return

    placeholders = ", ".join(["%s"] * len(columns))
    col_names = ", ".join(f'"{c}"' if c == "return" else c for c in columns)
    query = f"INSERT INTO {schema}.{table} ({col_names}) VALUES ({placeholders})"

    with conn.cursor() as cur:
        batch = []
        for row in rows:
            values = []
            for col in columns:
                val = row.get(col)
                # Convert dicts/lists to Json for JSONB columns
                if isinstance(val, (dict, list)):
                    values.append(Json(val))
                else:
                    values.append(val)
            batch.append(tuple(values))

        # Use executemany for simplicity; for very large datasets, consider execute_batch
        psycopg2.extras.execute_batch(cur, query, batch, page_size=500)

    conn.commit()


def insert_products(conn, schema: str, products: list[dict]):
    """Insert products into the database."""
    columns = [
        "id", "title", "body_html", "vendor", "product_type", "handle", "status",
        "tags", "template_suffix", "published_at", "published_scope", "created_at",
        "updated_at", "shop_url", "admin_graphql_api_id", "variants", "options",
        "image", "images", "total_inventory", "total_variants",
    ]
    # Strip internal meta fields
    clean_rows = [{k: v for k, v in row.items() if not k.startswith("_meta")} for row in products]
    bulk_insert(conn, schema, "products", clean_rows, columns)
    print(f"  Inserted {len(products)} products")


def insert_variants(conn, schema: str, variants: list[dict]):
    """Insert product variants into the database."""
    columns = [
        "id", "product_id", "title", "price", "compare_at_price", "sku", "barcode",
        "position", "option1", "option2", "option3", "grams", "weight", "weight_unit",
        "taxable", "tax_code", "inventory_item_id", "inventory_quantity",
        "old_inventory_quantity", "inventory_policy", "requires_shipping",
        "image_id", "image_src", "available_for_sale", "display_name",
        "admin_graphql_api_id", "created_at", "updated_at", "shop_url",
    ]
    bulk_insert(conn, schema, "product_variants", variants, columns)
    print(f"  Inserted {len(variants)} product variants")


def insert_customers(conn, schema: str, customers: list[dict]):
    """Insert customers into the database."""
    columns = [
        "id", "email", "first_name", "last_name", "phone", "state", "tags",
        "currency", "note", "verified_email", "tax_exempt", "tax_exemptions",
        "accepts_marketing", "accepts_marketing_updated_at", "marketing_opt_in_level",
        "orders_count", "total_spent", "last_order_id", "last_order_name",
        "admin_graphql_api_id", "created_at", "updated_at", "shop_url",
        "default_address", "addresses", "email_marketing_consent", "sms_marketing_consent",
    ]
    bulk_insert(conn, schema, "customers", customers, columns)
    print(f"  Inserted {len(customers)} customers")


def insert_orders(conn, schema: str, orders: list[dict]):
    """Insert orders into the database."""
    columns = [
        "id", "admin_graphql_api_id", "app_id", "browser_ip",
        "buyer_accepts_marketing", "cancel_reason", "cancelled_at", "cart_token",
        "checkout_id", "checkout_token", "closed_at", "confirmed",
        "confirmation_number", "contact_email", "created_at", "currency",
        "current_subtotal_price", "current_subtotal_price_set",
        "current_total_discounts", "current_total_discounts_set",
        "current_total_price", "current_total_price_set",
        "current_total_tax", "current_total_tax_set",
        "customer_locale", "discount_applications", "discount_codes",
        "email", "financial_status", "fulfillment_status", "landing_site",
        "name", "note", "note_attributes", "number", "order_number",
        "order_status_url", "payment_gateway_names", "phone",
        "presentment_currency", "processed_at", "source_name",
        "subtotal_price", "subtotal_price_set", "tags", "tax_exempt",
        "tax_lines", "taxes_included", "test", "token",
        "total_discounts", "total_discounts_set",
        "total_line_items_price", "total_line_items_price_set",
        "total_outstanding", "total_price", "total_price_set", "total_price_usd",
        "total_shipping_price_set", "total_tax", "total_tax_set",
        "total_tip_received", "total_weight", "updated_at",
        "customer", "billing_address", "shipping_address", "shipping_lines",
        "line_items", "fulfillments", "refunds", "shop_url",
    ]
    # Strip internal meta fields
    clean_rows = [{k: v for k, v in row.items() if not k.startswith("_meta")} for row in orders]
    bulk_insert(conn, schema, "orders", clean_rows, columns)
    print(f"  Inserted {len(orders)} orders")


def insert_refunds(conn, schema: str, refunds: list[dict]):
    """Insert order refunds into the database."""
    columns = [
        "id", "order_id", "admin_graphql_api_id", "created_at", "processed_at",
        "note", "restock", "user_id", "duties", "shop_url", "return",
        "total_duties_set", "order_adjustments", "refund_line_items", "transactions",
    ]
    bulk_insert(conn, schema, "order_refunds", refunds, columns)
    print(f"  Inserted {len(refunds)} refunds")


def insert_campaigns(conn, schema: str, campaigns: list[dict]):
    """Insert Meta Ads campaigns."""
    columns = [
        "id", "account_id", "name", "status", "effective_status", "configured_status",
        "objective", "buying_type", "bid_strategy", "daily_budget", "lifetime_budget",
        "budget_remaining", "spend_cap", "start_time", "stop_time", "created_time",
        "updated_time", "special_ad_category", "special_ad_category_country",
        "adlabels", "issues_info",
    ]
    clean_rows = [{k: v for k, v in row.items() if not k.startswith("_")} for row in campaigns]
    bulk_insert(conn, schema, "campaigns", clean_rows, columns)
    print(f"  Inserted {len(campaigns)} campaigns")


def insert_ad_sets(conn, schema: str, ad_sets: list[dict]):
    """Insert Meta Ads ad sets."""
    columns = [
        "id", "account_id", "campaign_id", "name", "effective_status",
        "daily_budget", "lifetime_budget", "budget_remaining", "bid_strategy",
        "bid_amount", "bid_constraints", "bid_info", "start_time", "end_time",
        "created_time", "updated_time", "targeting", "promoted_object",
        "adlabels", "learning_stage_info",
    ]
    clean_rows = [{k: v for k, v in row.items() if not k.startswith("_")} for row in ad_sets]
    bulk_insert(conn, schema, "ad_sets", clean_rows, columns)
    print(f"  Inserted {len(ad_sets)} ad sets")


def insert_ads(conn, schema: str, ads: list[dict]):
    """Insert Meta Ads ads."""
    columns = [
        "id", "account_id", "campaign_id", "adset_id", "name", "status",
        "effective_status", "bid_type", "bid_amount", "bid_info", "creative",
        "created_time", "updated_time", "last_updated_by_app_id", "source_ad_id",
        "targeting", "tracking_specs", "conversion_specs", "adlabels", "recommendations",
    ]
    clean_rows = [{k: v for k, v in row.items() if not k.startswith("_")} for row in ads]
    bulk_insert(conn, schema, "ads", clean_rows, columns)
    print(f"  Inserted {len(ads)} ads")


def insert_insights(conn, schema: str, insights: list[dict]):
    """Insert Meta Ads insights."""
    columns = [
        "date_start", "date_stop", "account_id", "account_name", "account_currency",
        "campaign_id", "campaign_name", "adset_id", "adset_name", "ad_id", "ad_name",
        "objective", "optimization_goal", "buying_type", "attribution_setting",
        "impressions", "clicks", "spend", "reach", "frequency",
        "cpc", "cpm", "cpp", "ctr", "unique_clicks", "unique_ctr",
        "cost_per_unique_click", "inline_link_clicks", "inline_link_click_ctr",
        "inline_post_engagement", "cost_per_inline_link_click",
        "cost_per_inline_post_engagement", "social_spend",
        "quality_ranking", "engagement_rate_ranking", "conversion_rate_ranking",
        "actions", "action_values", "conversions", "conversion_values",
        "cost_per_action_type", "cost_per_conversion",
        "purchase_roas", "website_purchase_roas", "outbound_clicks",
        "created_time", "updated_time",
    ]
    bulk_insert(conn, schema, "ads_insights", insights, columns)
    print(f"  Inserted {len(insights)} ads_insights rows")


def print_summary(conn, schema: str):
    """Print a summary of seeded data."""
    tables = [
        "products", "product_variants", "customers", "orders",
        "order_refunds", "campaigns", "ad_sets", "ads", "ads_insights",
    ]
    print("\n" + "=" * 60)
    print("SEED SUMMARY")
    print("=" * 60)

    with conn.cursor() as cur:
        for table in tables:
            cur.execute(f"SELECT COUNT(*) FROM {schema}.{table}")
            count = cur.fetchone()[0]
            print(f"  {schema}.{table:25s} {count:>8,} rows")

        # Revenue summary
        cur.execute(f"""
            SELECT
                COUNT(*) as order_count,
                SUM(CAST(total_price AS NUMERIC)) as total_revenue,
                AVG(CAST(total_price AS NUMERIC)) as avg_order_value
            FROM {schema}.orders
        """)
        row = cur.fetchone()
        print(f"\n  Shopify Orders:  {row[0]:,}")
        print(f"  Total Revenue:   ${row[1]:,.2f} AUD")
        print(f"  Avg Order Value: ${row[2]:,.2f} AUD")

        # Refund summary
        cur.execute(f"SELECT COUNT(*) FROM {schema}.order_refunds")
        refund_count = cur.fetchone()[0]
        print(f"  Refunds:         {refund_count} ({refund_count/row[0]*100:.1f}% of orders)")

        # Meta Ads summary
        cur.execute(f"""
            SELECT
                SUM(CAST(spend AS NUMERIC)) as total_spend,
                COUNT(DISTINCT campaign_id) as campaigns,
                COUNT(DISTINCT ad_id) as unique_ads,
                MIN(date_start) as first_date,
                MAX(date_start) as last_date
            FROM {schema}.ads_insights
        """)
        meta_row = cur.fetchone()
        print(f"\n  Meta Ad Spend:   ${meta_row[0]:,.2f} AUD")
        print(f"  Campaigns:       {meta_row[1]}")
        print(f"  Unique Ads:      {meta_row[2]}")
        print(f"  Date Range:      {meta_row[3]} to {meta_row[4]}")

        # Blended ROAS
        cur.execute(f"""
            SELECT
                SUM(
                    CASE WHEN elem->>'action_type' = 'purchase'
                    THEN CAST(elem->>'value' AS NUMERIC) ELSE 0 END
                ) as meta_revenue
            FROM {schema}.ads_insights,
                 jsonb_array_elements(action_values) AS elem
        """)
        meta_rev = float(cur.fetchone()[0] or 0)
        total_spend = float(meta_row[0]) if meta_row[0] else 0
        blended_roas = meta_rev / total_spend if total_spend > 0 else 0
        print(f"  Meta Revenue:    ${meta_rev:,.2f} AUD")
        print(f"  Meta ROAS:       {blended_roas:.2f}x")
        print(f"  Blended ROAS:    {float(row[1]) / total_spend:.2f}x" if total_spend > 0 else "  Blended ROAS:    N/A")

    print("=" * 60)


def main():
    args = parse_args()

    # Get DB URL
    db_url = args.db_url or get_db_url()
    schema = f"tenant_{args.tenant_id}"
    end_date = date(2026, 2, 19)  # Yesterday relative to "today" Feb 20, 2026
    start_date = end_date - timedelta(days=args.days - 1)

    print(f"\nSeed Configuration:")
    print(f"  Database:    {db_url.split('@')[1] if '@' in db_url else db_url}")
    print(f"  Schema:      {schema}")
    print(f"  Tenant ID:   {args.tenant_id}")
    print(f"  Date Range:  {start_date} to {end_date} ({args.days} days)")
    print(f"  Clean:       {args.clean}")
    print()

    conn = connect(db_url)

    try:
        # 1. Setup schema
        print("Setting up schema...")
        create_tenant(conn, args.tenant_id)
        setup_schema(conn, schema, clean=args.clean)
        create_tables(conn, schema)
        print()

        # 2. Generate Shopify data
        print("Generating Shopify data...")
        t0 = time.time()

        products, variants = generate_products(start_date)
        print(f"  Generated {len(products)} products, {len(variants)} variants")

        customers = generate_customers(num_customers=300, start_date=start_date)
        print(f"  Generated {len(customers)} customers")

        orders, refunds, daily_revenue = generate_orders(
            products=products,
            variants=variants,
            customers=customers,
            start_date=start_date,
            num_days=args.days,
        )
        print(f"  Generated {len(orders)} orders, {len(refunds)} refunds")
        print(f"  Shopify generation took {time.time() - t0:.1f}s")
        print()

        # 3. Generate Meta Ads data
        print("Generating Meta Ads data...")
        t0 = time.time()

        campaigns = generate_campaigns(start_date)
        print(f"  Generated {len(campaigns)} campaigns")

        ad_sets = generate_ad_sets(campaigns, start_date)
        print(f"  Generated {len(ad_sets)} ad sets")

        ads = generate_ads(ad_sets)
        print(f"  Generated {len(ads)} ads")

        insights = generate_ads_insights(
            ads=ads,
            start_date=start_date,
            num_days=args.days,
            daily_shopify_revenue=daily_revenue,
        )
        print(f"  Generated {len(insights)} ads_insights rows")
        print(f"  Meta Ads generation took {time.time() - t0:.1f}s")
        print()

        # 4. Insert all data
        print("Inserting data into PostgreSQL...")
        t0 = time.time()

        insert_products(conn, schema, products)
        insert_variants(conn, schema, variants)
        insert_customers(conn, schema, customers)
        insert_orders(conn, schema, orders)
        insert_refunds(conn, schema, refunds)
        insert_campaigns(conn, schema, campaigns)
        insert_ad_sets(conn, schema, ad_sets)
        insert_ads(conn, schema, ads)
        insert_insights(conn, schema, insights)

        print(f"  Insertion took {time.time() - t0:.1f}s")

        # 5. Print summary
        print_summary(conn, schema)

    finally:
        conn.close()

    print("\nDone! Database seeded successfully.")


if __name__ == "__main__":
    main()
