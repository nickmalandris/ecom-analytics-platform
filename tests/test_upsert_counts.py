"""
Tests for upsert insert/update/unchanged counting via xmax.

Verifies that upsert_rows correctly distinguishes new inserts from real updates
and unchanged rows using PostgreSQL's xmax system column and a WHERE clause
that skips updates when data is identical.

Tests run against the live database using a dedicated test schema.
"""

import psycopg2
import pytest

from src.ingestion.db_utils import upsert_rows, fmt_counts
from tests.conftest import DB_URL

TEST_SCHEMA = "tenant_upsert_test"

# Minimal table for testing — mirrors the products table structure
TEST_TABLE_DDL = f"""
CREATE TABLE IF NOT EXISTS {TEST_SCHEMA}.test_items (
    id BIGINT PRIMARY KEY,
    title TEXT,
    updated_at TIMESTAMPTZ
);
"""


@pytest.fixture(scope="module")
def conn():
    c = psycopg2.connect(DB_URL)
    c.autocommit = False
    with c.cursor() as cur:
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {TEST_SCHEMA}")
        cur.execute(TEST_TABLE_DDL)
    c.commit()
    yield c
    # Clean up
    with c.cursor() as cur:
        cur.execute(f"DROP SCHEMA {TEST_SCHEMA} CASCADE")
    c.commit()
    c.close()


class TestUpsertCounts:
    """Test that upsert_rows returns accurate inserted / updated / unchanged counts."""

    def _truncate(self, conn):
        with conn.cursor() as cur:
            cur.execute(f"TRUNCATE TABLE {TEST_SCHEMA}.test_items")
        conn.commit()

    def test_all_inserts(self, conn):
        """Fresh inserts into empty table should all be counted as inserted."""
        self._truncate(conn)
        rows = [
            {"id": 1, "title": "Product A", "updated_at": "2026-01-01T00:00:00Z"},
            {"id": 2, "title": "Product B", "updated_at": "2026-01-01T00:00:00Z"},
            {"id": 3, "title": "Product C", "updated_at": "2026-01-01T00:00:00Z"},
        ]
        result = upsert_rows(
            conn, TEST_SCHEMA, "test_items", ["id", "title", "updated_at"], rows
        )
        assert result == {"inserted": 3, "updated": 0, "unchanged": 0}

    def test_all_updates(self, conn):
        """Upserting existing rows with changed data should all be counted as updated."""
        self._truncate(conn)
        rows = [
            {"id": 10, "title": "Original A", "updated_at": "2026-01-01T00:00:00Z"},
            {"id": 11, "title": "Original B", "updated_at": "2026-01-01T00:00:00Z"},
        ]
        upsert_rows(conn, TEST_SCHEMA, "test_items", ["id", "title", "updated_at"], rows)

        rows_updated = [
            {"id": 10, "title": "Updated A", "updated_at": "2026-01-02T00:00:00Z"},
            {"id": 11, "title": "Updated B", "updated_at": "2026-01-02T00:00:00Z"},
        ]
        result = upsert_rows(
            conn, TEST_SCHEMA, "test_items", ["id", "title", "updated_at"], rows_updated
        )
        assert result == {"inserted": 0, "updated": 2, "unchanged": 0}

    def test_all_unchanged(self, conn):
        """Upserting identical data should report all rows as unchanged."""
        self._truncate(conn)
        rows = [
            {"id": 30, "title": "Same A", "updated_at": "2026-01-01T00:00:00Z"},
            {"id": 31, "title": "Same B", "updated_at": "2026-01-01T00:00:00Z"},
        ]
        upsert_rows(conn, TEST_SCHEMA, "test_items", ["id", "title", "updated_at"], rows)

        # Upsert exact same data again
        result = upsert_rows(
            conn, TEST_SCHEMA, "test_items", ["id", "title", "updated_at"], rows
        )
        assert result == {"inserted": 0, "updated": 0, "unchanged": 2}

    def test_mixed_inserts_and_updates(self, conn):
        """Batch with both new and changed existing rows should report both counts."""
        self._truncate(conn)
        rows = [
            {"id": 20, "title": "Existing A", "updated_at": "2026-01-01T00:00:00Z"},
            {"id": 21, "title": "Existing B", "updated_at": "2026-01-01T00:00:00Z"},
        ]
        upsert_rows(conn, TEST_SCHEMA, "test_items", ["id", "title", "updated_at"], rows)

        mixed = [
            {"id": 20, "title": "Updated A", "updated_at": "2026-01-02T00:00:00Z"},
            {"id": 21, "title": "Updated B", "updated_at": "2026-01-02T00:00:00Z"},
            {"id": 22, "title": "Brand New C", "updated_at": "2026-01-02T00:00:00Z"},
        ]
        result = upsert_rows(
            conn, TEST_SCHEMA, "test_items", ["id", "title", "updated_at"], mixed
        )
        assert result == {"inserted": 1, "updated": 2, "unchanged": 0}

    def test_mixed_all_three(self, conn):
        """Batch with inserts, updates, and unchanged rows."""
        self._truncate(conn)
        rows = [
            {"id": 40, "title": "Will Change", "updated_at": "2026-01-01T00:00:00Z"},
            {"id": 41, "title": "Will Stay", "updated_at": "2026-01-01T00:00:00Z"},
        ]
        upsert_rows(conn, TEST_SCHEMA, "test_items", ["id", "title", "updated_at"], rows)

        mixed = [
            {"id": 40, "title": "Changed!", "updated_at": "2026-01-02T00:00:00Z"},  # updated
            {"id": 41, "title": "Will Stay", "updated_at": "2026-01-01T00:00:00Z"},  # unchanged
            {"id": 42, "title": "Brand New", "updated_at": "2026-01-02T00:00:00Z"},  # inserted
        ]
        result = upsert_rows(
            conn, TEST_SCHEMA, "test_items", ["id", "title", "updated_at"], mixed
        )
        assert result == {"inserted": 1, "updated": 1, "unchanged": 1}

    def test_empty_rows(self, conn):
        """Empty input should return zero counts."""
        result = upsert_rows(
            conn, TEST_SCHEMA, "test_items", ["id", "title", "updated_at"], []
        )
        assert result == {"inserted": 0, "updated": 0, "unchanged": 0}

    def test_single_insert(self, conn):
        """Single new row should report 1 insert."""
        self._truncate(conn)
        rows = [{"id": 100, "title": "Solo", "updated_at": "2026-01-01T00:00:00Z"}]
        result = upsert_rows(
            conn, TEST_SCHEMA, "test_items", ["id", "title", "updated_at"], rows
        )
        assert result == {"inserted": 1, "updated": 0, "unchanged": 0}

    def test_single_update(self, conn):
        """Single existing row with changed data should report 1 update."""
        # Row 100 was inserted in previous test
        rows = [{"id": 100, "title": "Solo Updated", "updated_at": "2026-01-02T00:00:00Z"}]
        result = upsert_rows(
            conn, TEST_SCHEMA, "test_items", ["id", "title", "updated_at"], rows
        )
        assert result == {"inserted": 0, "updated": 1, "unchanged": 0}

    def test_single_unchanged(self, conn):
        """Single existing row with identical data should report 1 unchanged."""
        # Row 100 now has "Solo Updated" / 2026-01-02 from previous test
        rows = [{"id": 100, "title": "Solo Updated", "updated_at": "2026-01-02T00:00:00Z"}]
        result = upsert_rows(
            conn, TEST_SCHEMA, "test_items", ["id", "title", "updated_at"], rows
        )
        assert result == {"inserted": 0, "updated": 0, "unchanged": 1}

    def test_data_integrity_after_upsert(self, conn):
        """Verify actual data matches expected values after mixed upsert."""
        self._truncate(conn)
        rows = [
            {"id": 50, "title": "Original", "updated_at": "2026-01-01T00:00:00Z"},
        ]
        upsert_rows(conn, TEST_SCHEMA, "test_items", ["id", "title", "updated_at"], rows)

        mixed = [
            {"id": 50, "title": "Modified", "updated_at": "2026-01-02T00:00:00Z"},
            {"id": 51, "title": "New Item", "updated_at": "2026-01-02T00:00:00Z"},
        ]
        result = upsert_rows(
            conn, TEST_SCHEMA, "test_items", ["id", "title", "updated_at"], mixed
        )
        assert result == {"inserted": 1, "updated": 1, "unchanged": 0}

        with conn.cursor() as cur:
            cur.execute(
                f"SELECT id, title FROM {TEST_SCHEMA}.test_items ORDER BY id"
            )
            rows = cur.fetchall()
        assert rows == [(50, "Modified"), (51, "New Item")]

    def test_composite_key(self, conn):
        """Should handle composite primary keys."""
        schema = TEST_SCHEMA
        table = "test_composite"
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE {schema}.{table} (
                    k1 INT,
                    k2 INT,
                    val TEXT,
                    PRIMARY KEY (k1, k2)
                )
                """
            )
        conn.commit()

        # Insert
        rows = [{"k1": 1, "k2": 1, "val": "A"}, {"k1": 1, "k2": 2, "val": "B"}]
        res = upsert_rows(
            conn, schema, table, ["k1", "k2", "val"], rows, conflict_keys=["k1", "k2"]
        )
        assert res == {"inserted": 2, "updated": 0, "unchanged": 0}

        # Update one, leave one unchanged
        rows = [{"k1": 1, "k2": 1, "val": "A_updated"}, {"k1": 1, "k2": 2, "val": "B"}]
        res = upsert_rows(
            conn, schema, table, ["k1", "k2", "val"], rows, conflict_keys=["k1", "k2"]
        )
        assert res == {"inserted": 0, "updated": 1, "unchanged": 1}


class TestFmtCounts:
    """Test the fmt_counts helper for readable output."""

    # ── Incremental mode (default) ──────────────────

    def test_all_zeros(self):
        assert fmt_counts({"inserted": 0, "updated": 0, "unchanged": 0}) == "0"

    def test_inserts_only(self):
        assert fmt_counts({"inserted": 5, "updated": 0, "unchanged": 0}) == "5 new"

    def test_updates_only(self):
        assert fmt_counts({"inserted": 0, "updated": 3, "unchanged": 0}) == "3 updated"

    def test_unchanged_not_shown(self):
        """Unchanged rows are not displayed in incremental output."""
        assert fmt_counts({"inserted": 0, "updated": 0, "unchanged": 7}) == "0"

    def test_mixed_new_and_updated(self):
        result = fmt_counts({"inserted": 1, "updated": 2, "unchanged": 3})
        assert result == "1 new, 2 updated"

    def test_inserts_and_updates(self):
        result = fmt_counts({"inserted": 4, "updated": 1, "unchanged": 0})
        assert result == "4 new, 1 updated"

    # ── Full mode (shows total as "inserted") ───────

    def test_full_mode_shows_total_inserted(self):
        result = fmt_counts({"inserted": 10, "updated": 0, "unchanged": 0}, mode="full")
        assert result == "10 inserted"

    def test_full_mode_zeros(self):
        result = fmt_counts({"inserted": 0, "updated": 0, "unchanged": 0}, mode="full")
        assert result == "0"
