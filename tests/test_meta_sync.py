"""
Tests for Meta Ads sync orchestrator.

Uses mocked MetaClient and mocked DB connection.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.ingestion.meta_sync import (
    META_RESOURCE_KEYS,
    full_sync,
    incremental_sync,
)


@pytest.fixture
def mock_db_conn():
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = MagicMock()
    return conn


@pytest.fixture
def mock_meta_client():
    with patch("src.ingestion.meta_sync.MetaClient") as mock:
        client_instance = mock.return_value.__enter__.return_value
        # Default empty generators
        client_instance.get_campaigns.return_value = iter([[]])
        client_instance.get_ad_sets.return_value = iter([[]])
        client_instance.get_ads.return_value = iter([[]])
        client_instance.get_insights.return_value = iter([[]])
        yield client_instance


@pytest.fixture
def mock_upsert():
    with patch("src.ingestion.meta_sync.upsert_rows") as mock:
        mock.return_value = {"inserted": 0, "updated": 0, "unchanged": 0}
        yield mock


@pytest.fixture
def mock_helpers():
    with patch("src.ingestion.meta_sync.ensure_sync_state_table"), \
         patch("src.ingestion.meta_sync.mark_sync_started"), \
         patch("src.ingestion.meta_sync.mark_sync_completed"):
        yield


class TestMetaSync:
    def test_full_sync_calls_correct_methods(
        self, mock_db_conn, mock_meta_client, mock_upsert, mock_helpers
    ):
        """Full sync should truncate tables and call client with lifetime preset."""
        with patch("psycopg2.connect", return_value=mock_db_conn):
            res = full_sync(tenant_id=1, db_url="sqlite://")
        
        # Verify mode
        assert res["mode"] == "full"
        assert res["tenant_id"] == 1
        
        # Verify truncate called (4 tables)
        cursor = mock_db_conn.cursor.return_value.__enter__.return_value
        # 4 truncate calls. Tenant lookup and ensure_sync_state are mocked.
        assert cursor.execute.call_count == 4
        truncate_calls = [
            c for c in cursor.execute.call_args_list 
            if "TRUNCATE TABLE" in c[0][0]
        ]
        assert len(truncate_calls) == 4
        
        # Verify client calls
        mock_meta_client.get_campaigns.assert_called_once()
        mock_meta_client.get_ad_sets.assert_called_once()
        mock_meta_client.get_ads.assert_called_once()
        mock_meta_client.get_insights.assert_called_once_with(date_preset="lifetime", level="ad")

    def test_incremental_sync_calls_correct_methods(
        self, mock_db_conn, mock_meta_client, mock_upsert, mock_helpers
    ):
        """Incremental sync should NOT truncate and use last_7d preset."""
        with patch("psycopg2.connect", return_value=mock_db_conn):
            res = incremental_sync(tenant_id=1, db_url="sqlite://")
        
        # Verify mode
        assert res["mode"] == "incremental"
        
        # Verify NO truncate called
        cursor = mock_db_conn.cursor.return_value.__enter__.return_value
        truncate_calls = [
            c for c in cursor.execute.call_args_list 
            if "TRUNCATE TABLE" in c[0][0]
        ]
        assert len(truncate_calls) == 0
        
        # Verify client calls
        mock_meta_client.get_campaigns.assert_called_once()
        mock_meta_client.get_ad_sets.assert_called_once()
        mock_meta_client.get_ads.assert_called_once()
        mock_meta_client.get_insights.assert_called_once_with(date_preset="last_7d", level="ad")

    def test_sync_upserts_data(
        self, mock_db_conn, mock_meta_client, mock_upsert, mock_helpers
    ):
        """Sync should pass data from client to upsert_rows."""
        # Setup mock data
        mock_meta_client.get_campaigns.return_value = iter([
            [{"id": "c1", "name": "Campaign 1"}]
        ])
        mock_upsert.return_value = {"inserted": 1, "updated": 0, "unchanged": 0}

        with patch("psycopg2.connect", return_value=mock_db_conn):
            res = incremental_sync(tenant_id=1, db_url="sqlite://")
        
        # Verify upsert called for campaigns
        upsert_calls = mock_upsert.call_args_list
        campaign_call = next(c for c in upsert_calls if c[0][2] == "campaigns")
        assert campaign_call[0][4] == [{"id": "c1", "name": "Campaign 1"}]
        assert res["campaigns"] == {"inserted": 1, "updated": 0, "unchanged": 0}

    def test_insights_composite_key(
        self, mock_db_conn, mock_meta_client, mock_upsert, mock_helpers
    ):
        """Insights upsert should use composite key."""
        mock_meta_client.get_insights.return_value = iter([
            [{"date_start": "2026-01-01", "account_id": "1", "ad_id": "a1"}]
        ])

        with patch("psycopg2.connect", return_value=mock_db_conn):
            incremental_sync(tenant_id=1, db_url="sqlite://")
        
        # Verify upsert called with correct conflict keys
        upsert_calls = mock_upsert.call_args_list
        insights_call = next(c for c in upsert_calls if c[0][2] == "ads_insights")
        assert insights_call.kwargs["conflict_keys"] == ["date_start", "account_id", "ad_id"]
