"""
Tests for API endpoints.

Uses FastAPI TestClient against the live database.
"""

import pytest
from fastapi.testclient import TestClient

from tests.conftest import ADMIN_API_KEY, TENANT_API_KEY


class TestHealthEndpoint:
    def test_health_check(self, api_client):
        resp = api_client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "database": "ok"}


class TestAuthMiddleware:
    def test_no_api_key_returns_401(self, api_client):
        resp = api_client.get("/api/tenants")
        assert resp.status_code == 401

    def test_bad_api_key_returns_403(self, api_client):
        resp = api_client.get("/api/tenants", headers={"X-API-Key": "bad_key"})
        assert resp.status_code == 403

    def test_tenant_key_cannot_list_tenants(self, api_client):
        resp = api_client.get("/api/tenants", headers={"X-API-Key": TENANT_API_KEY})
        assert resp.status_code == 403

    def test_admin_key_can_list_tenants(self, api_client):
        resp = api_client.get("/api/tenants", headers={"X-API-Key": ADMIN_API_KEY})
        assert resp.status_code == 200


class TestTenantEndpoints:
    def test_list_tenants(self, api_client):
        resp = api_client.get("/api/tenants", headers={"X-API-Key": ADMIN_API_KEY})
        assert resp.status_code == 200
        tenants = resp.json()
        assert isinstance(tenants, list)
        assert len(tenants) >= 1

    def test_get_own_tenant(self, api_client):
        resp = api_client.get("/api/tenants/me", headers={"X-API-Key": TENANT_API_KEY})
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 1
        assert data["name"] is not None and len(data["name"]) > 0

    def test_get_tenant_by_id(self, api_client):
        resp = api_client.get("/api/tenants/1", headers={"X-API-Key": ADMIN_API_KEY})
        assert resp.status_code == 200
        assert resp.json()["name"] is not None and len(resp.json()["name"]) > 0

    def test_get_nonexistent_tenant(self, api_client):
        resp = api_client.get("/api/tenants/9999", headers={"X-API-Key": ADMIN_API_KEY})
        assert resp.status_code == 404

    def test_create_and_delete_tenant(self, api_client):
        """Create a tenant then clean up."""
        # Create
        resp = api_client.post(
            "/api/tenants",
            headers={"X-API-Key": ADMIN_API_KEY},
            json={
                "name": "Test Tenant Pytest",
                "email_recipients": ["test@example.com"],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Tenant Pytest"
        assert data["api_key"].startswith("sk_")
        tenant_id = data["id"]

        # Verify it exists
        resp = api_client.get(f"/api/tenants/{tenant_id}", headers={"X-API-Key": ADMIN_API_KEY})
        assert resp.status_code == 200

        # Update
        resp = api_client.patch(
            f"/api/tenants/{tenant_id}",
            headers={"X-API-Key": ADMIN_API_KEY},
            json={"name": "Updated Tenant Name"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Tenant Name"

        # Delete
        resp = api_client.delete(f"/api/tenants/{tenant_id}", headers={"X-API-Key": ADMIN_API_KEY})
        assert resp.status_code == 204

        # Verify gone
        resp = api_client.get(f"/api/tenants/{tenant_id}", headers={"X-API-Key": ADMIN_API_KEY})
        assert resp.status_code == 404

    def test_admin_key_cannot_get_own_tenant(self, api_client):
        """Admin key has no tenant profile, should get 400."""
        resp = api_client.get("/api/tenants/me", headers={"X-API-Key": ADMIN_API_KEY})
        assert resp.status_code == 400
