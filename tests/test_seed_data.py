"""
Tests verifying seed data integrity in the database.

Ensures the seed script populated correct volumes and the data
matches expected characteristics.
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


class TestSeedDataIntegrity:
    """Verify seed data volumes and structure."""

    def test_tenant_exists(self, conn):
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, api_key FROM public.tenants WHERE id = %s", (TENANT_ID,))
            row = cur.fetchone()
        assert row is not None
        assert row[1] == "Test Store AU"
        assert row[2] == "sk_test_analytics_key_001"

    def test_orders_count(self, conn):
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM raw_tenant_{TENANT_ID}.orders")
            count = cur.fetchone()[0]
        # Seed generates ~2,072 orders (deterministic with seed=42)
        assert 2000 <= count <= 2200, f"Expected ~2072 orders, got {count}"

    def test_products_count(self, conn):
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM raw_tenant_{TENANT_ID}.products")
            count = cur.fetchone()[0]
        assert count == 20

    def test_customers_count(self, conn):
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM raw_tenant_{TENANT_ID}.customers")
            count = cur.fetchone()[0]
        assert count == 300

    def test_refunds_exist(self, conn):
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM raw_tenant_{TENANT_ID}.order_refunds")
            count = cur.fetchone()[0]
        assert 100 <= count <= 200, f"Expected ~143 refunds, got {count}"

    def test_meta_campaigns_count(self, conn):
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM raw_tenant_{TENANT_ID}.campaigns")
            count = cur.fetchone()[0]
        assert count == 6

    def test_meta_ad_sets_count(self, conn):
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM raw_tenant_{TENANT_ID}.ad_sets")
            count = cur.fetchone()[0]
        assert count == 16

    def test_meta_ads_count(self, conn):
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM raw_tenant_{TENANT_ID}.ads")
            count = cur.fetchone()[0]
        assert count == 43

    def test_meta_insights_count(self, conn):
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM raw_tenant_{TENANT_ID}.ads_insights")
            count = cur.fetchone()[0]
        assert 2400 <= count <= 2700, f"Expected ~2529 insights, got {count}"

    def test_orders_have_airbyte_columns(self, conn):
        with conn.cursor() as cur:
            cur.execute(
                f"""SELECT _airbyte_raw_id, _airbyte_extracted_at, _airbyte_meta
                    FROM raw_tenant_{TENANT_ID}.orders LIMIT 1"""
            )
            row = cur.fetchone()
        assert row is not None
        assert row[0] is not None  # _airbyte_raw_id
        assert row[1] is not None  # _airbyte_extracted_at
        assert row[2] is not None  # _airbyte_meta (JSONB)

    def test_orders_currency_is_aud(self, conn):
        with conn.cursor() as cur:
            cur.execute(
                f"""SELECT DISTINCT currency
                    FROM raw_tenant_{TENANT_ID}.orders"""
            )
            currencies = [row[0] for row in cur.fetchall()]
        assert currencies == ["AUD"]

    def test_product_variants_exist(self, conn):
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM raw_tenant_{TENANT_ID}.product_variants")
            count = cur.fetchone()[0]
        assert count == 78
