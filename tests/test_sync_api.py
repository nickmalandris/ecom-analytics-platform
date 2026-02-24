"""
Tests for the sync API endpoints.
"""

from unittest.mock import patch

import pytest

from tests.conftest import ADMIN_API_KEY, TENANT_API_KEY


class TestSyncEndpoints:
    def test_trigger_sync_no_auth(self, api_client):
        resp = api_client.post("/api/sync/shopify", json={"mode": "incremental"})
        assert resp.status_code == 401

    def test_trigger_sync_bad_mode(self, api_client):
        resp = api_client.post(
            "/api/sync/shopify",
            headers={"X-API-Key": TENANT_API_KEY},
            json={"mode": "invalid"},
        )
        assert resp.status_code == 400

    def test_trigger_sync_admin_cannot_use_tenant_endpoint(self, api_client):
        resp = api_client.post(
            "/api/sync/shopify",
            headers={"X-API-Key": ADMIN_API_KEY},
            json={"mode": "incremental"},
        )
        assert resp.status_code == 400

    @patch("src.ingestion.shopify_sync.incremental_sync")
    def test_trigger_sync_admin_endpoint(self, mock_sync, api_client):
        """Admin can trigger sync for a specific tenant."""
        mock_sync.return_value = None
        resp = api_client.post(
            "/api/sync/shopify/1",
            headers={"X-API-Key": ADMIN_API_KEY},
            json={"mode": "incremental"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "triggered"
        mock_sync.assert_called_once_with(1)

    @patch("src.ingestion.meta_sync.incremental_sync")
    def test_trigger_meta_sync(self, mock_sync, api_client):
        """Tenant can trigger Meta sync."""
        mock_sync.return_value = None
        resp = api_client.post(
            "/api/sync/meta",
            headers={"X-API-Key": TENANT_API_KEY},
            json={"mode": "incremental"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "triggered"
        mock_sync.assert_called_once_with(1)

    @patch("src.ingestion.meta_sync.full_sync")
    def test_trigger_meta_sync_admin(self, mock_sync, api_client):
        """Admin can trigger Meta sync for tenant."""
        mock_sync.return_value = None
        resp = api_client.post(
            "/api/sync/meta/1",
            headers={"X-API-Key": ADMIN_API_KEY},
            json={"mode": "full"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "triggered"
        mock_sync.assert_called_once_with(1)

    def test_get_sync_status(self, api_client):
        resp = api_client.get(
            "/api/sync/status",
            headers={"X-API-Key": TENANT_API_KEY},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == 1
        assert isinstance(data["resources"], list)

    def test_get_sync_status_admin(self, api_client):
        resp = api_client.get(
            "/api/sync/status/1",
            headers={"X-API-Key": ADMIN_API_KEY},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == 1
