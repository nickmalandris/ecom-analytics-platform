"""
Tests for Shopify client token management.

Validates:
  - Client credentials grant token acquisition
  - Automatic token refresh on expiry
  - 401 handling with token refresh and retry
  - Static token mode (no auto-refresh)
  - Error handling for bad credentials
"""

import time
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.ingestion.shopify_client import (
    ShopifyClient,
    ShopifyClientError,
    TOKEN_EXPIRY_BUFFER_SECONDS,
)


# ─── Helpers ─────────────────────────────────────────────


def _mock_token_response(token: str = "test_token_123", expires_in: int = 86399):
    """Build a mock httpx.Response for a successful token grant."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = {
        "access_token": token,
        "scope": "read_orders,read_products",
        "expires_in": expires_in,
    }
    resp.raise_for_status = MagicMock()
    return resp


def _mock_graphql_response(data: dict | None = None):
    """Build a mock httpx.Response for a GraphQL query."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = {
        "data": data or {"shop": {"name": "Test Store"}},
        "extensions": {
            "cost": {
                "throttleStatus": {
                    "currentlyAvailable": 900,
                    "restoreRate": 50.0,
                }
            }
        },
    }
    resp.raise_for_status = MagicMock()
    return resp


def _mock_401_response():
    """Build a mock 401 response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 401
    resp.text = "Unauthorized"
    return resp


ENV_VARS = {
    "SHOPIFY_STORE_URL": "test-store.myshopify.com",
    "SHOPIFY_CLIENT_ID": "test_client_id",
    "SHOPIFY_SECRET_KEY": "test_client_secret",
}


# ─── Tests ───────────────────────────────────────────────


class TestClientCredentialsGrant:
    """Test initial token acquisition via client credentials."""

    @patch.dict("os.environ", ENV_VARS, clear=False)
    @patch("src.ingestion.shopify_client.httpx.post")
    def test_obtains_token_on_init(self, mock_post):
        """Client should obtain a token via client credentials on init."""
        mock_post.return_value = _mock_token_response("fresh_token")

        client = ShopifyClient()
        assert client._token == "fresh_token"
        assert not client._static_token

        # Verify the POST was made to the correct endpoint
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert "admin/oauth/access_token" in call_kwargs.args[0]
        assert call_kwargs.kwargs["data"]["grant_type"] == "client_credentials"
        assert call_kwargs.kwargs["data"]["client_id"] == "test_client_id"
        assert call_kwargs.kwargs["data"]["client_secret"] == "test_client_secret"
        client.close()

    @patch.dict("os.environ", ENV_VARS, clear=False)
    @patch("src.ingestion.shopify_client.httpx.post")
    def test_stores_expiry_with_buffer(self, mock_post):
        """Token expiry should account for the safety buffer."""
        mock_post.return_value = _mock_token_response(expires_in=86399)

        before = time.time()
        client = ShopifyClient()
        after = time.time()

        expected_min = before + 86399 - TOKEN_EXPIRY_BUFFER_SECONDS
        expected_max = after + 86399 - TOKEN_EXPIRY_BUFFER_SECONDS
        assert expected_min <= client._token_expires_at <= expected_max
        client.close()

    @patch.dict("os.environ", {
        "SHOPIFY_STORE_URL": "test-store.myshopify.com",
        "SHOPIFY_CLIENT_ID": "",
        "SHOPIFY_SECRET_KEY": "",
    }, clear=False)
    def test_raises_without_credentials(self):
        """Should raise error when no credentials are available."""
        with pytest.raises(ShopifyClientError, match="No Shopify credentials"):
            ShopifyClient()

    @patch.dict("os.environ", ENV_VARS, clear=False)
    @patch("src.ingestion.shopify_client.httpx.post")
    def test_raises_on_failed_grant(self, mock_post):
        """Should raise error when client credentials grant fails."""
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 401
        resp.text = "Invalid credentials"
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "401", request=MagicMock(), response=resp
        )
        mock_post.return_value = resp

        with pytest.raises(ShopifyClientError, match="Client credentials grant failed"):
            ShopifyClient()


class TestStaticToken:
    """Test explicit access_token mode (no auto-refresh)."""

    @patch.dict("os.environ", {"SHOPIFY_STORE_URL": "test-store.myshopify.com"}, clear=False)
    def test_static_token_no_refresh(self):
        """Explicit token should be used as-is without calling credentials endpoint."""
        client = ShopifyClient(access_token="static_token_abc")
        assert client._token == "static_token_abc"
        assert client._static_token is True
        assert client._token_expires_at == 0.0
        client.close()

    @patch.dict("os.environ", {"SHOPIFY_STORE_URL": "test-store.myshopify.com"}, clear=False)
    def test_get_token_returns_static(self):
        """_get_token should return the static token without refresh."""
        client = ShopifyClient(access_token="my_static_token")
        assert client._get_token() == "my_static_token"
        client.close()


class TestTokenAutoRefresh:
    """Test automatic token refresh when token expires."""

    @patch.dict("os.environ", ENV_VARS, clear=False)
    @patch("src.ingestion.shopify_client.httpx.post")
    def test_get_token_refreshes_on_expiry(self, mock_post):
        """_get_token should refresh when token is expired."""
        # First call: initial token
        mock_post.return_value = _mock_token_response("token_1")
        client = ShopifyClient()
        assert client._token == "token_1"

        # Force expiry
        client._token_expires_at = time.time() - 1

        # Second call: refresh
        mock_post.return_value = _mock_token_response("token_2")
        token = client._get_token()
        assert token == "token_2"
        assert mock_post.call_count == 2
        client.close()

    @patch.dict("os.environ", ENV_VARS, clear=False)
    @patch("src.ingestion.shopify_client.httpx.post")
    def test_get_token_no_refresh_when_valid(self, mock_post):
        """_get_token should NOT refresh when token is still valid."""
        mock_post.return_value = _mock_token_response("token_1")
        client = ShopifyClient()

        # Token should still be valid (expires in ~24h)
        token = client._get_token()
        assert token == "token_1"
        assert mock_post.call_count == 1  # Only the initial grant
        client.close()


class TestExecuteWith401Retry:
    """Test that execute() handles 401 by refreshing token and retrying."""

    @patch.dict("os.environ", ENV_VARS, clear=False)
    @patch("src.ingestion.shopify_client.httpx.post")
    def test_401_triggers_refresh_and_retry(self, mock_token_post):
        """On 401, should refresh token and retry the request."""
        mock_token_post.return_value = _mock_token_response("initial_token")
        client = ShopifyClient()

        # Mock the HTTP client's post method
        mock_http_post = MagicMock()
        # First call: 401, second call (after refresh): success
        mock_http_post.side_effect = [
            _mock_401_response(),
            _mock_graphql_response({"shop": {"name": "Refreshed"}}),
        ]
        client._http.post = mock_http_post

        # Also mock the refresh to return a new token
        mock_token_post.return_value = _mock_token_response("refreshed_token")

        result = client.execute("{ shop { name } }")
        assert result == {"shop": {"name": "Refreshed"}}

        # Should have called HTTP post twice (401 + retry)
        assert mock_http_post.call_count == 2

        # Second call should use the refreshed token
        second_call_headers = mock_http_post.call_args_list[1].kwargs.get("headers", {})
        assert second_call_headers["X-Shopify-Access-Token"] == "refreshed_token"
        client.close()

    @patch.dict("os.environ", ENV_VARS, clear=False)
    @patch("src.ingestion.shopify_client.httpx.post")
    def test_401_with_static_token_raises(self, mock_token_post):
        """Static tokens should not attempt refresh on 401."""
        client = ShopifyClient(
            store_url="test-store.myshopify.com",
            access_token="bad_static_token",
        )

        mock_http_post = MagicMock()
        mock_http_post.return_value = _mock_401_response()
        client._http.post = mock_http_post

        with pytest.raises(ShopifyClientError, match="401 Unauthorized"):
            client.execute("{ shop { name } }")
        client.close()

    @patch.dict("os.environ", ENV_VARS, clear=False)
    @patch("src.ingestion.shopify_client.httpx.post")
    def test_double_401_raises(self, mock_token_post):
        """If refresh succeeds but second request still 401s, should raise."""
        mock_token_post.return_value = _mock_token_response("initial_token")
        client = ShopifyClient()

        mock_http_post = MagicMock()
        # Both attempts return 401
        mock_http_post.return_value = _mock_401_response()
        client._http.post = mock_http_post

        # Refresh will succeed but second request still fails
        mock_token_post.return_value = _mock_token_response("refreshed_token")

        with pytest.raises(ShopifyClientError, match="401 Unauthorized"):
            client.execute("{ shop { name } }")
        client.close()


class TestExecuteTokenInjection:
    """Test that execute() injects token per-request."""

    @patch.dict("os.environ", ENV_VARS, clear=False)
    @patch("src.ingestion.shopify_client.httpx.post")
    def test_token_sent_in_header(self, mock_token_post):
        """Each request should include the current token in headers."""
        mock_token_post.return_value = _mock_token_response("my_token")
        client = ShopifyClient()

        mock_http_post = MagicMock()
        mock_http_post.return_value = _mock_graphql_response()
        client._http.post = mock_http_post

        client.execute("{ shop { name } }")

        call_kwargs = mock_http_post.call_args
        assert call_kwargs.kwargs["headers"]["X-Shopify-Access-Token"] == "my_token"
        client.close()
