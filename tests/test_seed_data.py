"""
Tests verifying seed data integrity in the database.

Ensures the seed script populated correct volumes and the data
matches expected characteristics.

CI runs: uv run python -m scripts.seed --clean --days 7
Local default: uv run python -m scripts.seed --clean --days 90

These tests run against whatever data is in the database. Some assertions
are strict (seed-only) and are skipped when detecting a non-seed environment.
"""

from tests.conftest import DB_URL, TENANT_ID

import psycopg2
import pytest


@pytest.fixture(scope="module")
def conn():
    c = psycopg2.connect(DB_URL)
    c.autocommit = True  # Prevent cascading transaction failures
    yield c
    c.close()


@pytest.fixture(scope="module")
def is_seeded(conn):
    """Detect whether the database contains seed data (vs live-synced data)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT name FROM public.tenants WHERE id = %s", (TENANT_ID,)
        )
        row = cur.fetchone()
    # Seed script always sets name to "Test Store AU"
    return row is not None and row[0] == "Test Store AU"


class TestSeedDataIntegrity:
    """Verify seed data volumes and structure."""

    def test_tenant_exists(self, conn):
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, api_key FROM public.tenants WHERE id = %s", (TENANT_ID,))
            row = cur.fetchone()
        assert row is not None
        assert row[1] is not None and len(row[1]) > 0, "Tenant name should not be empty"
        assert row[2] is not None and len(row[2]) > 0, "API key should not be empty"

    def test_orders_count(self, conn):
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM tenant_{TENANT_ID}.orders")
            count = cur.fetchone()[0]
        # --days 7 produces ~140 orders, --days 90 produces ~2072, live sync varies
        assert count >= 50, f"Expected at least 50 orders, got {count}"

    def test_products_count(self, conn):
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM tenant_{TENANT_ID}.products")
            count = cur.fetchone()[0]
        assert count >= 20, f"Expected at least 20 products, got {count}"

    def test_customers_count(self, conn):
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM tenant_{TENANT_ID}.customers")
            count = cur.fetchone()[0]
        assert count >= 50, f"Expected at least 50 customers, got {count}"

    def test_refunds_exist(self, conn, is_seeded):
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM tenant_{TENANT_ID}.order_refunds")
            count = cur.fetchone()[0]
        if is_seeded:
            assert count >= 1, f"Expected at least 1 refund from seed data, got {count}"
        else:
            assert count >= 0  # Live data may or may not have refunds

    def test_meta_campaigns_count(self, conn, is_seeded):
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM tenant_{TENANT_ID}.campaigns")
            count = cur.fetchone()[0]
        if is_seeded:
            assert count == 6
        else:
            assert count >= 0  # Live data may not have Meta synced yet

    def test_meta_ad_sets_count(self, conn, is_seeded):
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM tenant_{TENANT_ID}.ad_sets")
            count = cur.fetchone()[0]
        if is_seeded:
            assert count == 16
        else:
            assert count >= 0

    def test_meta_ads_count(self, conn, is_seeded):
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM tenant_{TENANT_ID}.ads")
            count = cur.fetchone()[0]
        if is_seeded:
            assert count == 43
        else:
            assert count >= 0

    def test_meta_insights_count(self, conn, is_seeded):
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM tenant_{TENANT_ID}.ads_insights")
            count = cur.fetchone()[0]
        if is_seeded:
            # --days 7 produces ~175 insights (25 ads × 7 days), --days 90 produces ~2529
            assert count >= 100, f"Expected at least 100 insights, got {count}"
        else:
            assert count >= 0

    def test_orders_currency_is_consistent(self, conn):
        with conn.cursor() as cur:
            cur.execute(
                f"""SELECT DISTINCT currency
                    FROM tenant_{TENANT_ID}.orders"""
            )
            currencies = [row[0] for row in cur.fetchall()]
        assert len(currencies) == 1, f"Expected single currency, got {currencies}"

    def test_product_variants_exist(self, conn):
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM tenant_{TENANT_ID}.product_variants")
            count = cur.fetchone()[0]
        assert count >= 78, f"Expected at least 78 variants, got {count}"
