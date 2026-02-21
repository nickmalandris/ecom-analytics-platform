"""
Shopify data sync orchestrator.

Two sync modes:
  - Full sync (--full): Uses Bulk Operations API for initial load.
    Truncates raw Shopify tables and re-inserts everything.
  - Incremental sync (--incremental): Uses paginated GraphQL queries.
    Pulls records updated since last sync and upserts.

Usage:
    uv run python -m src.ingestion.shopify_sync --tenant-id 1 --full
    uv run python -m src.ingestion.shopify_sync --tenant-id 1 --incremental
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from psycopg2.extras import Json

from src.ingestion.shopify_bulk import ShopifyBulkClient
from src.ingestion.shopify_client import ShopifyClient, ShopifyClientError
from src.ingestion.shopify_queries import (
    CUSTOMERS_BULK,
    CUSTOMERS_PAGINATED,
    ORDERS_BULK,
    ORDERS_PAGINATED,
    PRODUCTS_BULK,
    PRODUCTS_PAGINATED,
)
from src.ingestion.shopify_transform import (
    transform_customer,
    transform_order,
    transform_product,
)
from src.ingestion.sync_state import (
    ensure_sync_state_table,
    get_last_sync,
    is_sync_running,
    mark_sync_completed,
    mark_sync_failed,
    mark_sync_started,
)

logger = logging.getLogger(__name__)

# ─── DB helpers ──────────────────────────────────────────


def _get_db_url() -> str:
    return os.getenv(
        "DATABASE_URL",
        "postgresql://analytics_user:analytics_pass@localhost:5435/analytics",
    )


def _get_tenant_store_url(conn: psycopg2.extensions.connection, tenant_id: int) -> str | None:
    """Look up the Shopify store URL for a tenant."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT shopify_store_url FROM public.tenants WHERE id = %s",
            (tenant_id,),
        )
        row = cur.fetchone()
    return row[0] if row else None


def _upsert_products(conn, schema: str, products: list[dict]) -> int:
    """Upsert product rows into the raw table."""
    if not products:
        return 0
    columns = [
        "id", "title", "body_html", "vendor", "product_type", "handle", "status",
        "tags", "template_suffix", "published_at", "published_scope", "created_at",
        "updated_at", "shop_url", "admin_graphql_api_id", "variants", "options",
        "image", "images", "total_inventory", "total_variants",
        "_airbyte_raw_id", "_airbyte_extracted_at", "_airbyte_meta",
    ]
    return _upsert_rows(conn, schema, "products", columns, products, conflict_col="id")


def _upsert_variants(conn, schema: str, variants: list[dict]) -> int:
    """Upsert product variant rows."""
    if not variants:
        return 0
    columns = [
        "id", "product_id", "title", "price", "compare_at_price", "sku", "barcode",
        "position", "option1", "option2", "option3", "grams", "weight", "weight_unit",
        "taxable", "tax_code", "inventory_item_id", "inventory_quantity",
        "old_inventory_quantity", "inventory_policy", "requires_shipping",
        "image_id", "image_src", "available_for_sale", "display_name",
        "admin_graphql_api_id", "created_at", "updated_at", "shop_url",
        "_airbyte_raw_id", "_airbyte_extracted_at", "_airbyte_meta",
    ]
    return _upsert_rows(conn, schema, "product_variants", columns, variants, conflict_col="id")


def _upsert_customers(conn, schema: str, customers: list[dict]) -> int:
    """Upsert customer rows."""
    if not customers:
        return 0
    columns = [
        "id", "email", "first_name", "last_name", "phone", "state", "tags",
        "currency", "note", "verified_email", "tax_exempt", "tax_exemptions",
        "accepts_marketing", "accepts_marketing_updated_at", "marketing_opt_in_level",
        "orders_count", "total_spent", "last_order_id", "last_order_name",
        "admin_graphql_api_id", "created_at", "updated_at", "shop_url",
        "default_address", "addresses", "email_marketing_consent", "sms_marketing_consent",
        "_airbyte_raw_id", "_airbyte_extracted_at", "_airbyte_meta",
    ]
    return _upsert_rows(conn, schema, "customers", columns, customers, conflict_col="id")


def _upsert_orders(conn, schema: str, orders: list[dict]) -> int:
    """Upsert order rows."""
    if not orders:
        return 0
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
        "_airbyte_raw_id", "_airbyte_extracted_at", "_airbyte_meta",
    ]
    return _upsert_rows(conn, schema, "orders", columns, orders, conflict_col="id")


def _upsert_refunds(conn, schema: str, refunds: list[dict]) -> int:
    """Upsert refund rows."""
    if not refunds:
        return 0
    columns = [
        "id", "order_id", "admin_graphql_api_id", "created_at", "processed_at",
        "note", "restock", "user_id", "duties", "shop_url", "return",
        "total_duties_set", "order_adjustments", "refund_line_items", "transactions",
        "_airbyte_raw_id", "_airbyte_extracted_at", "_airbyte_meta",
    ]
    return _upsert_rows(conn, schema, "order_refunds", columns, refunds, conflict_col="id")


def _upsert_rows(
    conn,
    schema: str,
    table: str,
    columns: list[str],
    rows: list[dict],
    conflict_col: str = "id",
) -> int:
    """
    Generic upsert: INSERT ... ON CONFLICT DO UPDATE.

    Returns the number of rows upserted.
    """
    if not rows:
        return 0

    col_names = ", ".join(f'"{c}"' if c == "return" else c for c in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    update_cols = [c for c in columns if c != conflict_col and not c.startswith("_airbyte")]
    update_set = ", ".join(
        f'"{c}" = EXCLUDED."{c}"' if c == "return" else f"{c} = EXCLUDED.{c}"
        for c in update_cols
    )

    sql = (
        f"INSERT INTO {schema}.{table} ({col_names}) VALUES ({placeholders}) "
        f"ON CONFLICT ({conflict_col}) DO UPDATE SET {update_set}"
    )

    batch = []
    for row in rows:
        values = []
        for col in columns:
            val = row.get(col)
            if isinstance(val, (dict, list)):
                values.append(Json(val))
            else:
                values.append(val)
        batch.append(tuple(values))

    with conn.cursor() as cur:
        psycopg2.extras.execute_batch(cur, sql, batch, page_size=500)
    conn.commit()

    return len(batch)


def _truncate_shopify_tables(conn, schema: str) -> None:
    """Truncate all Shopify raw tables for a clean full sync."""
    tables = ["order_refunds", "orders", "customers", "product_variants", "products"]
    with conn.cursor() as cur:
        for table in tables:
            cur.execute(f"TRUNCATE TABLE {schema}.{table} CASCADE")
    conn.commit()
    logger.info(f"Truncated Shopify tables in {schema}")


def _backfill_refunds(conn, tenant_id: int, store_url: str) -> int:
    """
    Backfill detailed refund data using paginated API.
    
    Bulk API cannot fetch nested refund line items/transactions due to limitations.
    We fetch all refunded/partially_refunded orders via standard API to fill gaps.
    """
    logger.info("Backfilling refund details via paginated API...")
    schema = f"raw_tenant_{tenant_id}"
    query_filter = "financial_status:refunded OR financial_status:partially_refunded"
    
    total_orders = 0
    with ShopifyClient(store_url=store_url) as client:
        order_rows, refund_rows = [], []
        
        # Reuse ORDERS_PAGINATED which fetches full details
        for page in client.paginate(ORDERS_PAGINATED, "orders", query_filter=query_filter):
            for node in page:
                o_row, r_rows = transform_order(node, store_url)
                order_rows.append(o_row)
                refund_rows.extend(r_rows)
            
            # Flush batch
            if order_rows:
                _upsert_orders(conn, schema, order_rows)
                _upsert_refunds(conn, schema, refund_rows)
                total_orders += len(order_rows)
                order_rows, refund_rows = [], []
                
    logger.info(f"Backfilled {total_orders} refunded orders with full details")
    return total_orders


# ─── Full Sync (Bulk Operations) ────────────────────────


def full_sync(tenant_id: int, db_url: str | None = None) -> dict:
    """
    Full sync via Shopify Bulk Operations API.
    
    Steps:
      1. Submit bulk queries for products, customers, orders
      2. Poll until complete
      3. Download and stream-parse JSONL files
      4. Transform and insert into raw tables (after truncating)
      5. Backfill detailed refund data via paginated API (workaround for Bulk API limits)

    Returns a summary dict with record counts.
    """
    load_dotenv()
    db_url = db_url or _get_db_url()
    conn = psycopg2.connect(db_url)
    schema = f"raw_tenant_{tenant_id}"

    try:
        ensure_sync_state_table(conn)

        # Get store URL
        store_url = _get_tenant_store_url(conn, tenant_id)
        if not store_url:
            store_url = os.getenv("SHOPIFY_STORE_URL", "")
        if not store_url:
            raise ShopifyClientError("No Shopify store URL configured for this tenant")

        # Check for running syncs
        for resource in ["products", "customers", "orders"]:
            if is_sync_running(conn, tenant_id, resource):
                raise ShopifyClientError(f"Sync already running for {resource}")

        logger.info(f"Starting full sync for tenant {tenant_id} ({store_url})")
        sync_start = datetime.now(timezone.utc)

        with ShopifyClient(store_url=store_url) as client:
            bulk = ShopifyBulkClient(client)
            summary = {"mode": "full", "tenant_id": tenant_id}

            # ── Products ────────────────────────────
            mark_sync_started(conn, tenant_id, "products")
            try:
                logger.info("Bulk syncing products...")
                jsonl_path = bulk.execute_bulk_query(PRODUCTS_BULK, query_filter="")

                product_rows = []
                variant_rows = []
                for parent in ShopifyBulkClient.reassemble_with_children(
                    jsonl_path, "Product", [{"type": "ProductVariant", "field": "variants"}]
                ):
                    p_row, v_rows = transform_product(parent, store_url)
                    product_rows.append(p_row)
                    variant_rows.extend(v_rows)

                # Truncate and insert
                with conn.cursor() as cur:
                    cur.execute(f"TRUNCATE TABLE {schema}.product_variants CASCADE")
                    cur.execute(f"TRUNCATE TABLE {schema}.products CASCADE")
                conn.commit()

                _upsert_products(conn, schema, product_rows)
                _upsert_variants(conn, schema, variant_rows)
                mark_sync_completed(conn, tenant_id, "products", len(product_rows), sync_start)
                summary["products"] = len(product_rows)
                summary["product_variants"] = len(variant_rows)
                logger.info(f"Products: {len(product_rows)}, Variants: {len(variant_rows)}")

                # Clean up temp file
                jsonl_path.unlink(missing_ok=True)
            except Exception as e:
                mark_sync_failed(conn, tenant_id, "products", str(e))
                raise

            # ── Customers ───────────────────────────
            mark_sync_started(conn, tenant_id, "customers")
            try:
                logger.info("Bulk syncing customers...")
                jsonl_path = bulk.execute_bulk_query(CUSTOMERS_BULK, query_filter="")

                customer_rows = []
                # Use reassemble to handle addressesV2 connection children
                for parent in ShopifyBulkClient.reassemble_with_children(
                    jsonl_path,
                    "Customer",
                    [{"type": "MailingAddress", "field": "addressesV2"}]
                ):
                    customer_rows.append(transform_customer(parent, store_url))

                with conn.cursor() as cur:
                    cur.execute(f"TRUNCATE TABLE {schema}.customers CASCADE")
                conn.commit()

                _upsert_customers(conn, schema, customer_rows)
                mark_sync_completed(conn, tenant_id, "customers", len(customer_rows), sync_start)
                summary["customers"] = len(customer_rows)
                logger.info(f"Customers: {len(customer_rows)}")

                jsonl_path.unlink(missing_ok=True)
            except Exception as e:
                mark_sync_failed(conn, tenant_id, "customers", str(e))
                raise

            # ── Orders + Refunds ────────────────────
            mark_sync_started(conn, tenant_id, "orders")
            try:
                logger.info("Bulk syncing orders...")
                # Bulk query (lean refunds)
                jsonl_path = bulk.execute_bulk_query(ORDERS_BULK, query_filter="")

                order_rows = []
                refund_rows = []

                # Orders are top-level in JSONL; child line items / refunds
                # are on separate lines with __parentId.
                # Since our order query requests lineItems and refunds inline,
                # the bulk JSONL will interleave them.
                # We use reassemble_with_children to recombine.
                for parent in ShopifyBulkClient.reassemble_with_children(
                    jsonl_path,
                    "Order",
                    [
                        {"type": "LineItem", "field": "lineItems"},
                        {"type": "Refund", "field": "refunds"},
                    ],
                ):
                    # Re-wrap lineItems/refunds as connections for the transformer
                    # since the transformer expects the GraphQL paginated format
                    o_row, r_rows = transform_order(parent, store_url)
                    order_rows.append(o_row)
                    refund_rows.extend(r_rows)

                with conn.cursor() as cur:
                    cur.execute(f"TRUNCATE TABLE {schema}.order_refunds CASCADE")
                    cur.execute(f"TRUNCATE TABLE {schema}.orders CASCADE")
                conn.commit()

                _upsert_orders(conn, schema, order_rows)
                _upsert_refunds(conn, schema, refund_rows)
                
                # Backfill detailed refund data
                backfilled_count = _backfill_refunds(conn, tenant_id, store_url)
                
                mark_sync_completed(conn, tenant_id, "orders", len(order_rows), sync_start)
                mark_sync_started(conn, tenant_id, "order_refunds")
                mark_sync_completed(conn, tenant_id, "order_refunds", len(refund_rows), sync_start)
                summary["orders"] = len(order_rows)
                summary["order_refunds"] = len(refund_rows)
                summary["backfilled_refund_orders"] = backfilled_count
                logger.info(f"Orders: {len(order_rows)}, Refunds: {len(refund_rows)}")

                jsonl_path.unlink(missing_ok=True)
            except Exception as e:
                mark_sync_failed(conn, tenant_id, "orders", str(e))
                raise

        elapsed = (datetime.now(timezone.utc) - sync_start).total_seconds()
        summary["elapsed_seconds"] = round(elapsed, 1)
        logger.info(f"Full sync completed in {elapsed:.1f}s: {summary}")
        return summary

    finally:
        conn.close()


# ─── Incremental Sync (Paginated Queries) ───────────────


def incremental_sync(tenant_id: int, db_url: str | None = None) -> dict:
    """
    Incremental sync via paginated GraphQL queries.

    Pulls records updated since the last sync and upserts them.
    If no prior sync exists, falls back to full_sync automatically.

    Returns a summary dict with record counts.
    """
    load_dotenv()
    db_url = db_url or _get_db_url()
    conn = psycopg2.connect(db_url)
    schema = f"raw_tenant_{tenant_id}"

    try:
        ensure_sync_state_table(conn)

        # Check if we have a prior sync — if not, do full sync
        last_product_sync = get_last_sync(conn, tenant_id, "products")
        if last_product_sync is None:
            logger.info("No prior sync found — falling back to full sync")
            conn.close()
            return full_sync(tenant_id, db_url)

        store_url = _get_tenant_store_url(conn, tenant_id)
        if not store_url:
            store_url = os.getenv("SHOPIFY_STORE_URL", "")
        if not store_url:
            raise ShopifyClientError("No Shopify store URL configured for this tenant")

        logger.info(f"Starting incremental sync for tenant {tenant_id}")
        sync_start = datetime.now(timezone.utc)
        summary = {"mode": "incremental", "tenant_id": tenant_id}

        with ShopifyClient(store_url=store_url) as client:

            # ── Products ────────────────────────────
            last_sync = get_last_sync(conn, tenant_id, "products")
            mark_sync_started(conn, tenant_id, "products")
            try:
                query_filter = f"updated_at:>{last_sync.isoformat()}" if last_sync else None
                product_rows, variant_rows = [], []

                for page in client.paginate(
                    PRODUCTS_PAGINATED, "products", query_filter=query_filter
                ):
                    for node in page:
                        p_row, v_rows = transform_product(node, store_url)
                        product_rows.append(p_row)
                        variant_rows.extend(v_rows)

                _upsert_products(conn, schema, product_rows)
                _upsert_variants(conn, schema, variant_rows)
                mark_sync_completed(conn, tenant_id, "products", len(product_rows), sync_start)
                summary["products"] = len(product_rows)
                summary["product_variants"] = len(variant_rows)
                logger.info(f"Products: {len(product_rows)}, Variants: {len(variant_rows)}")
            except Exception as e:
                mark_sync_failed(conn, tenant_id, "products", str(e))
                raise

            # ── Customers ───────────────────────────
            last_sync = get_last_sync(conn, tenant_id, "customers")
            mark_sync_started(conn, tenant_id, "customers")
            try:
                query_filter = f"updated_at:>{last_sync.isoformat()}" if last_sync else None
                customer_rows = []

                for page in client.paginate(
                    CUSTOMERS_PAGINATED, "customers", query_filter=query_filter
                ):
                    for node in page:
                        customer_rows.append(transform_customer(node, store_url))

                _upsert_customers(conn, schema, customer_rows)
                mark_sync_completed(conn, tenant_id, "customers", len(customer_rows), sync_start)
                summary["customers"] = len(customer_rows)
                logger.info(f"Customers: {len(customer_rows)}")
            except Exception as e:
                mark_sync_failed(conn, tenant_id, "customers", str(e))
                raise

            # ── Orders + Refunds ────────────────────
            last_sync = get_last_sync(conn, tenant_id, "orders")
            mark_sync_started(conn, tenant_id, "orders")
            try:
                query_filter = f"updated_at:>{last_sync.isoformat()}" if last_sync else None
                order_rows, refund_rows = [], []

                for page in client.paginate(
                    ORDERS_PAGINATED, "orders", query_filter=query_filter
                ):
                    for node in page:
                        o_row, r_rows = transform_order(node, store_url)
                        order_rows.append(o_row)
                        refund_rows.extend(r_rows)

                _upsert_orders(conn, schema, order_rows)
                _upsert_refunds(conn, schema, refund_rows)
                mark_sync_completed(conn, tenant_id, "orders", len(order_rows), sync_start)
                mark_sync_started(conn, tenant_id, "order_refunds")
                mark_sync_completed(conn, tenant_id, "order_refunds", len(refund_rows), sync_start)
                summary["orders"] = len(order_rows)
                summary["order_refunds"] = len(refund_rows)
                logger.info(f"Orders: {len(order_rows)}, Refunds: {len(refund_rows)}")
            except Exception as e:
                mark_sync_failed(conn, tenant_id, "orders", str(e))
                raise

        elapsed = (datetime.now(timezone.utc) - sync_start).total_seconds()
        summary["elapsed_seconds"] = round(elapsed, 1)
        logger.info(f"Incremental sync completed in {elapsed:.1f}s: {summary}")
        return summary

    finally:
        conn.close()


# ─── CLI ─────────────────────────────────────────────────


def parse_args():
    parser = argparse.ArgumentParser(description="Sync Shopify data via GraphQL API")
    parser.add_argument("--tenant-id", type=int, default=1, help="Tenant ID")
    parser.add_argument("--db-url", type=str, default=None, help="Database URL")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--full", action="store_true", help="Full sync (bulk operations)")
    mode.add_argument("--incremental", action="store_true", help="Incremental sync (paginated)")
    return parser.parse_args()


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    args = parse_args()
    load_dotenv()
    db_url = args.db_url or _get_db_url()

    try:
        if args.full:
            result = full_sync(args.tenant_id, db_url)
        else:
            result = incremental_sync(args.tenant_id, db_url)

        print(f"\nSync complete: {json.dumps(result, indent=2)}")
    except ShopifyClientError as e:
        print(f"\nSync failed: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}", file=sys.stderr)
        logger.exception("Sync failed with unexpected error")
        sys.exit(1)


if __name__ == "__main__":
    main()
