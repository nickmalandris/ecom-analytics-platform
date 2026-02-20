"""
Tests for the data query layer used by the agent tools.

Validates that queries return expected shapes and reasonable values
from the materialized views.
"""

from datetime import date

import psycopg2
import pytest

from src.data import queries
from tests.conftest import DB_URL, TENANT_ID

# Full 90-day data range
START = date(2025, 11, 22)
END = date(2026, 2, 19)

# A typical week for focused tests
WEEK_START = date(2026, 2, 10)
WEEK_END = date(2026, 2, 16)


@pytest.fixture(scope="module")
def conn():
    c = psycopg2.connect(DB_URL)
    yield c
    c.close()


class TestRevenueSummary:
    def test_returns_dict(self, conn):
        result = queries.get_revenue_summary(conn, TENANT_ID, WEEK_START, WEEK_END)
        assert isinstance(result, dict)

    def test_has_required_keys(self, conn):
        result = queries.get_revenue_summary(conn, TENANT_ID, WEEK_START, WEEK_END)
        for key in ["gross_revenue", "net_revenue", "avg_order_value", "total_discounts"]:
            assert key in result, f"Missing key: {key}"

    def test_revenue_is_positive(self, conn):
        result = queries.get_revenue_summary(conn, TENANT_ID, WEEK_START, WEEK_END)
        assert float(result["gross_revenue"]) > 0
        assert float(result["net_revenue"]) > 0

    def test_aov_is_reasonable(self, conn):
        result = queries.get_revenue_summary(conn, TENANT_ID, WEEK_START, WEEK_END)
        aov = float(result["avg_order_value"])
        # AOV should be between $50 and $500 AUD for our product mix
        assert 50 <= aov <= 500, f"AOV {aov} is out of expected range"


class TestOrdersAndRefunds:
    def test_returns_dict(self, conn):
        result = queries.get_orders_and_refunds(conn, TENANT_ID, WEEK_START, WEEK_END)
        assert isinstance(result, dict)

    def test_has_order_count(self, conn):
        result = queries.get_orders_and_refunds(conn, TENANT_ID, WEEK_START, WEEK_END)
        assert "total_orders" in result
        assert int(result["total_orders"]) > 0

    def test_refund_rate_under_100_percent(self, conn):
        result = queries.get_orders_and_refunds(conn, TENANT_ID, WEEK_START, WEEK_END)
        if "refund_rate" in result and result["refund_rate"] is not None:
            assert float(result["refund_rate"]) < 100


class TestAdPerformance:
    def test_returns_list(self, conn):
        result = queries.get_ad_performance(conn, TENANT_ID, WEEK_START, WEEK_END)
        assert isinstance(result, list)

    def test_has_campaigns(self, conn):
        result = queries.get_ad_performance(conn, TENANT_ID, WEEK_START, WEEK_END)
        assert len(result) > 0

    def test_campaign_has_spend(self, conn):
        result = queries.get_ad_performance(conn, TENANT_ID, WEEK_START, WEEK_END)
        for campaign in result:
            assert "spend" in campaign or "total_spend" in campaign


class TestBlendedMetrics:
    def test_returns_dict(self, conn):
        result = queries.get_blended_metrics(conn, TENANT_ID, WEEK_START, WEEK_END)
        assert isinstance(result, dict)

    def test_has_blended_roas(self, conn):
        result = queries.get_blended_metrics(conn, TENANT_ID, WEEK_START, WEEK_END)
        assert "blended_roas" in result or "mer" in result


class TestTopProducts:
    def test_returns_list(self, conn):
        result = queries.get_top_products(conn, TENANT_ID, WEEK_START, WEEK_END)
        assert isinstance(result, list)

    def test_respects_limit(self, conn):
        result = queries.get_top_products(conn, TENANT_ID, WEEK_START, WEEK_END, limit=5)
        assert len(result) <= 5

    def test_products_have_revenue(self, conn):
        result = queries.get_top_products(conn, TENANT_ID, WEEK_START, WEEK_END, limit=3)
        for product in result:
            assert "revenue" in product or "total_revenue" in product


class TestProblemProducts:
    def test_returns_list(self, conn):
        result = queries.get_problem_products(conn, TENANT_ID, START, END)
        assert isinstance(result, list)

    def test_merino_wool_jumper_flagged(self, conn):
        """The seed data has Merino Wool Jumper with ~22% refund rate — it should be flagged."""
        result = queries.get_problem_products(conn, TENANT_ID, START, END)
        product_names = [p.get("product_title", p.get("title", "")).lower() for p in result]
        assert any("merino" in name or "wool" in name or "jumper" in name for name in product_names), (
            f"Expected Merino Wool Jumper to be flagged. Got: {product_names}"
        )


class TestCustomerMetrics:
    def test_returns_dict(self, conn):
        result = queries.get_customer_metrics(conn, TENANT_ID, WEEK_START, WEEK_END)
        assert isinstance(result, dict)

    def test_has_customer_counts(self, conn):
        result = queries.get_customer_metrics(conn, TENANT_ID, WEEK_START, WEEK_END)
        # Should have some form of new/returning breakdown
        keys = set(result.keys())
        assert len(keys) > 0


class TestComparePeriods:
    def test_returns_dict(self, conn):
        result = queries.compare_periods(
            conn, TENANT_ID,
            WEEK_START, WEEK_END,
            date(2026, 2, 3), date(2026, 2, 9),
        )
        assert isinstance(result, dict)

    def test_has_change_metrics(self, conn):
        result = queries.compare_periods(
            conn, TENANT_ID,
            WEEK_START, WEEK_END,
            date(2026, 2, 3), date(2026, 2, 9),
        )
        # Should contain current and previous period values
        assert len(result) > 0
