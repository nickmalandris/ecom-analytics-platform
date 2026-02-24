"""
Database utilities and schema management.
"""

import os
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

# Re-export generic utilities for backward compatibility
from src.ingestion.db_utils import upsert_rows, fmt_counts, fmt_summary, get_db_url

# DDL Constants (extracted from seed.py)
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
    Fully initialize a new tenant's database schema.
    Creates the schema and all required tables for Shopify and Meta data.
    """
    schema = f"tenant_{tenant_id}"
    
    # List of table DDLs to execute
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
        # Create Schema
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        
        # Create Tables
        for table_name, ddl in ddl_statements:
            cur.execute(ddl.format(schema=schema))
            
    conn.commit()
