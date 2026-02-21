"""
Tests for the sync state tracking module.

Tests run against the live database.
"""

from datetime import datetime, timezone

import psycopg2
import pytest

from src.ingestion.sync_state import (
    ensure_sync_state_table,
    get_last_sync,
    get_sync_status,
    is_sync_running,
    mark_sync_completed,
    mark_sync_failed,
    mark_sync_started,
)
from tests.conftest import DB_URL

# Use a test tenant ID that won't conflict with real data
TEST_TENANT_ID = 9999


@pytest.fixture(scope="module")
def conn():
    c = psycopg2.connect(DB_URL)
    c.autocommit = True
    ensure_sync_state_table(c)
    yield c
    # Clean up test data
    with c.cursor() as cur:
        cur.execute("DELETE FROM public.sync_state WHERE tenant_id = %s", (TEST_TENANT_ID,))
    c.close()


class TestSyncState:
    def test_table_exists(self, conn):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = 'sync_state')"
            )
            assert cur.fetchone()[0] is True

    def test_no_prior_sync_returns_none(self, conn):
        result = get_last_sync(conn, TEST_TENANT_ID, "products")
        assert result is None

    def test_mark_started(self, conn):
        mark_sync_started(conn, TEST_TENANT_ID, "products")
        assert is_sync_running(conn, TEST_TENANT_ID, "products") is True

    def test_mark_completed(self, conn):
        now = datetime.now(timezone.utc)
        mark_sync_completed(conn, TEST_TENANT_ID, "products", 100, now)
        assert is_sync_running(conn, TEST_TENANT_ID, "products") is False
        last = get_last_sync(conn, TEST_TENANT_ID, "products")
        assert last is not None

    def test_mark_failed(self, conn):
        mark_sync_started(conn, TEST_TENANT_ID, "customers")
        mark_sync_failed(conn, TEST_TENANT_ID, "customers", "Test error")
        assert is_sync_running(conn, TEST_TENANT_ID, "customers") is False

    def test_get_sync_status(self, conn):
        status = get_sync_status(conn, TEST_TENANT_ID)
        assert isinstance(status, list)
        assert len(status) >= 1
        # Should have our products and customers entries
        resource_names = [s["resource"] for s in status]
        assert "products" in resource_names

    def test_idempotent_table_creation(self, conn):
        """Calling ensure_sync_state_table multiple times should not error."""
        ensure_sync_state_table(conn)
        ensure_sync_state_table(conn)
