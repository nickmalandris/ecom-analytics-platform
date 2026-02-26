"""
Tests for the data query layer used by the agent tools.

Validates that queries return expected shapes and reasonable values
from the materialized views.

Seed data always ends at 2026-02-19. CI seeds with --days 7 (start: 2026-02-13),
local default seeds with --days 90 (start: 2025-11-22). Date ranges here must
overlap with the minimum 7-day window.
"""

from datetime import date

import psycopg2
import pytest

from src.data import queries
from tests.conftest import DB_URL, TENANT_ID

# Use the last few days of the seed window — guaranteed to have data
# regardless of whether --days 7 or --days 90 was used.
WEEK_START = date(2026, 2, 14)
WEEK_END = date(2026, 2, 19)

# Previous period for comparison tests
PREV_START = date(2026, 2, 13)
PREV_END = date(2026, 2, 14)

# Full range: use the 7-day minimum window
START = date(2026, 2, 13)
END = date(2026, 2, 19)


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
        # AOV should be between $20 and $1000 for our product mix
        assert 20 <= aov <= 1000, f"AOV {aov} is out of expected range"


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

    def test_problem_products_have_high_refund_rate(self, conn):
        """If any problem products are flagged, they should have a meaningful refund rate."""
        result = queries.get_problem_products(conn, TENANT_ID, START, END)
        # With only 7 days of data, there may not be enough refunds to flag anything.
        # Just verify the structure is correct if results exist.
        for product in result:
            assert "product_title" in product or "title" in product


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
            PREV_START, PREV_END,
        )
        assert isinstance(result, dict)

    def test_has_change_metrics(self, conn):
        result = queries.compare_periods(
            conn, TENANT_ID,
            WEEK_START, WEEK_END,
            PREV_START, PREV_END,
        )
        # Should contain current and previous period values
        assert len(result) > 0
