"""
Tests for Meta Marketing API client.

All tests use mocked HTTP responses — no live API calls.
"""

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.ingestion.meta_client import (
    BASE_URL,
    MetaClient,
    MetaClientError,
    MetaRateLimitError,
    MetaTokenExpiredError,
)


# ─── Fixtures ─────────────────────────────────────────────


@pytest.fixture
def mock_exchange():
    """Mock the token exchange HTTP call."""
    with patch("src.ingestion.meta_client.httpx.get") as mock_get:
        mock_get.return_value = httpx.Response(
            200,
            json={
                "access_token": "long_lived_token_abc",
                "token_type": "bearer",
                "expires_in": 5184000,  # 60 days
            },
            request=httpx.Request("GET", "https://graph.facebook.com/oauth/access_token"),
        )
        yield mock_get


@pytest.fixture
def client(mock_exchange):
    """Create a MetaClient with mocked token exchange."""
    c = MetaClient(
        ad_account_id="act_12345",
        app_id="test_app_id",
        app_secret="test_app_secret",
        short_lived_token="test_short_token",
    )
    # Replace the httpx client with a mock for subsequent calls
    c._http = MagicMock()
    yield c
    c.close()


@pytest.fixture
def static_client():
    """Create a MetaClient with a static access token (no exchange)."""
    c = MetaClient(
        ad_account_id="act_12345",
        access_token="static_token_xyz",
    )
    c._http = MagicMock()
    yield c
    c.close()


# ─── Initialization Tests ────────────────────────────────


class TestInit:
    def test_no_account_id_raises(self):
        """Should raise if no ad account ID is provided."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(MetaClientError, match="No Meta ad account ID"):
                MetaClient(ad_account_id="", access_token="tok")

    def test_no_credentials_raises(self):
        """Should raise if no token or credentials are provided."""
        with patch.dict("os.environ", {"META_AD_ACCOUNT_ID": "act_123"}, clear=True):
            with pytest.raises(MetaClientError, match="No Meta credentials"):
                MetaClient()

    def test_act_prefix_added(self, mock_exchange):
        """Should add act_ prefix if missing."""
        c = MetaClient(
            ad_account_id="12345",
            app_id="app",
            app_secret="secret",
            short_lived_token="tok",
        )
        assert c.ad_account_id == "act_12345"
        c.close()

    def test_act_prefix_preserved(self, mock_exchange):
        """Should not double-prefix if act_ already present."""
        c = MetaClient(
            ad_account_id="act_12345",
            app_id="app",
            app_secret="secret",
            short_lived_token="tok",
        )
        assert c.ad_account_id == "act_12345"
        c.close()

    def test_static_token_init(self):
        """Should use explicit token as-is without exchange."""
        c = MetaClient(
            ad_account_id="act_123",
            access_token="my_static_token",
        )
        assert c._token == "my_static_token"
        assert c._static_token is True
        c.close()


# ─── Token Exchange Tests ────────────────────────────────


class TestTokenExchange:
    def test_successful_exchange(self, mock_exchange):
        """Should exchange short-lived token for long-lived token."""
        c = MetaClient(
            ad_account_id="act_123",
            app_id="app_id",
            app_secret="app_secret",
            short_lived_token="short_tok",
        )
        assert c._token == "long_lived_token_abc"
        assert c._static_token is False
        c.close()

        # Verify the exchange request
        mock_exchange.assert_called_once()
        call_kwargs = mock_exchange.call_args
        assert call_kwargs.kwargs["params"]["grant_type"] == "fb_exchange_token"
        assert call_kwargs.kwargs["params"]["client_id"] == "app_id"

    def test_exchange_failure_raises(self):
        """Should raise MetaClientError on exchange failure."""
        with patch("src.ingestion.meta_client.httpx.get") as mock_get:
            mock_get.return_value = httpx.Response(
                400,
                json={"error": {"message": "Invalid token"}},
                request=httpx.Request("GET", "https://example.com"),
            )
            with pytest.raises(MetaClientError, match="Token exchange failed"):
                MetaClient(
                    ad_account_id="act_123",
                    app_id="app_id",
                    app_secret="secret",
                    short_lived_token="short_tok",
                )

    def test_exchange_no_token_in_response(self):
        """Should raise if exchange response has no access_token."""
        with patch("src.ingestion.meta_client.httpx.get") as mock_get:
            mock_get.return_value = httpx.Response(
                200,
                json={"token_type": "bearer"},
                request=httpx.Request("GET", "https://example.com"),
            )
            with pytest.raises(MetaClientError, match="No access_token"):
                MetaClient(
                    ad_account_id="act_123",
                    app_id="app_id",
                    app_secret="secret",
                    short_lived_token="short_tok",
                )


# ─── GET Request Tests ───────────────────────────────────


class TestGet:
    def test_basic_get(self, client):
        """Should make a GET request and return parsed JSON."""
        client._http.get.return_value = httpx.Response(
            200,
            json={"data": [{"id": "1", "name": "Campaign 1"}]},
            headers={},
            request=httpx.Request("GET", "https://example.com"),
        )
        result = client.get("act_12345/campaigns", params={"fields": "id,name"})
        assert result == {"data": [{"id": "1", "name": "Campaign 1"}]}

    def test_full_url_passthrough(self, client):
        """Should use full URL directly if it starts with http."""
        full_url = "https://graph.facebook.com/v25.0/act_12345/campaigns?after=abc"
        client._http.get.return_value = httpx.Response(
            200,
            json={"data": []},
            headers={},
            request=httpx.Request("GET", full_url),
        )
        client.get(full_url)
        call_args = client._http.get.call_args
        assert call_args.args[0] == full_url

    def test_rate_limit_error_retries(self, client):
        """Should retry on rate-limit errors (code 17)."""
        rate_limit_resp = httpx.Response(
            400,
            json={"error": {"code": 17, "message": "Too many calls"}},
            headers={},
            request=httpx.Request("GET", "https://example.com"),
        )
        success_resp = httpx.Response(
            200,
            json={"data": [{"id": "1"}]},
            headers={},
            request=httpx.Request("GET", "https://example.com"),
        )
        client._http.get.side_effect = [rate_limit_resp, success_resp]

        with patch("src.ingestion.meta_client.time.sleep"):
            result = client.get("act_12345/campaigns")

        assert result == {"data": [{"id": "1"}]}
        assert client._http.get.call_count == 2

    def test_token_expired_triggers_refresh(self, client):
        """Should attempt token refresh on 190 error."""
        expired_resp = httpx.Response(
            400,
            json={"error": {"code": 190, "message": "Token expired"}},
            headers={},
            request=httpx.Request("GET", "https://example.com"),
        )
        success_resp = httpx.Response(
            200,
            json={"data": []},
            headers={},
            request=httpx.Request("GET", "https://example.com"),
        )
        client._http.get.side_effect = [expired_resp, success_resp]

        with patch.object(client, "_exchange_token") as mock_refresh:
            mock_refresh.return_value = ("new_token", 6000000)  # > 7 days buffer
            with patch("src.ingestion.meta_client.time.sleep"):
                result = client.get("act_12345/campaigns")

        mock_refresh.assert_called_once()
        assert result == {"data": []}

    def test_token_expired_static_raises(self, static_client):
        """Should raise immediately on 190 with static token (can't refresh)."""
        expired_resp = httpx.Response(
            400,
            json={"error": {"code": 190, "message": "Token expired"}},
            headers={},
            request=httpx.Request("GET", "https://example.com"),
        )
        static_client._http.get.return_value = expired_resp

        with pytest.raises(MetaTokenExpiredError, match="Token expired"):
            static_client.get("act_12345/campaigns")

    def test_max_retries_exceeded(self, client):
        """Should raise after max retries."""
        rate_limit_resp = httpx.Response(
            400,
            json={"error": {"code": 17, "message": "Too many calls"}},
            headers={},
            request=httpx.Request("GET", "https://example.com"),
        )
        client._http.get.return_value = rate_limit_resp

        with patch("src.ingestion.meta_client.time.sleep"):
            with pytest.raises(MetaClientError, match="Max retries"):
                client.get("act_12345/campaigns")

    def test_http_error_retries(self, client):
        """Should retry on httpx transport errors."""
        client._http.get.side_effect = [
            httpx.ConnectError("Connection refused", request=httpx.Request("GET", "https://example.com")),
            httpx.Response(200, json={"data": []}, headers={}, request=httpx.Request("GET", "https://example.com")),
        ]

        with patch("src.ingestion.meta_client.time.sleep"):
            result = client.get("act_12345/campaigns")

        assert result == {"data": []}

    def test_non_retryable_error_raises(self, client):
        """Should raise immediately on non-retryable API errors."""
        error_resp = httpx.Response(
            400,
            json={"error": {"code": 100, "message": "Invalid parameter"}},
            headers={},
            request=httpx.Request("GET", "https://example.com"),
        )
        client._http.get.return_value = error_resp

        with pytest.raises(MetaClientError, match="Invalid parameter"):
            client.get("act_12345/campaigns")


# ─── Rate Limit Check Tests ─────────────────────────────


class TestRateLimitCheck:
    def test_no_header_no_sleep(self, client):
        """Should not sleep when x-app-usage header is absent."""
        resp = httpx.Response(200, headers={})
        with patch("src.ingestion.meta_client.time.sleep") as mock_sleep:
            client._check_rate_limit(resp)
        mock_sleep.assert_not_called()

    def test_low_usage_no_sleep(self, client):
        """Should not sleep when usage is below threshold."""
        usage = json.dumps({"call_count": 10, "total_cputime": 5, "total_time": 8})
        resp = httpx.Response(200, headers={"x-app-usage": usage})
        with patch("src.ingestion.meta_client.time.sleep") as mock_sleep:
            client._check_rate_limit(resp)
        mock_sleep.assert_not_called()

    def test_high_usage_sleeps(self, client):
        """Should sleep when usage exceeds threshold."""
        usage = json.dumps({"call_count": 85, "total_cputime": 20, "total_time": 30})
        resp = httpx.Response(200, headers={"x-app-usage": usage})
        with patch("src.ingestion.meta_client.time.sleep") as mock_sleep:
            client._check_rate_limit(resp)
        mock_sleep.assert_called_once()
        # 85 - 75 = 10, * 2 = 20 seconds
        assert mock_sleep.call_args.args[0] == 20

    def test_malformed_header_ignored(self, client):
        """Should gracefully handle malformed x-app-usage header."""
        resp = httpx.Response(200, headers={"x-app-usage": "not-json"})
        with patch("src.ingestion.meta_client.time.sleep") as mock_sleep:
            client._check_rate_limit(resp)
        mock_sleep.assert_not_called()


# ─── Pagination Tests ────────────────────────────────────


class TestPaginate:
    def test_single_page(self, client):
        """Should yield one page when there's no next URL."""
        client._http.get.return_value = httpx.Response(
            200,
            json={
                "data": [{"id": "1"}, {"id": "2"}],
                "paging": {"cursors": {"after": "abc"}},
            },
            headers={},
            request=httpx.Request("GET", "https://example.com"),
        )
        pages = list(client.paginate("act_12345/campaigns"))
        assert len(pages) == 1
        assert len(pages[0]) == 2

    def test_multi_page(self, client):
        """Should follow paging.next URLs across multiple pages."""
        page1 = httpx.Response(
            200,
            json={
                "data": [{"id": "1"}],
                "paging": {
                    "cursors": {"after": "cursor1"},
                    "next": "https://graph.facebook.com/v25.0/act_12345/campaigns?after=cursor1",
                },
            },
            headers={},
            request=httpx.Request("GET", "https://example.com"),
        )
        page2 = httpx.Response(
            200,
            json={
                "data": [{"id": "2"}],
                "paging": {"cursors": {"after": "cursor2"}},
            },
            headers={},
            request=httpx.Request("GET", "https://example.com"),
        )
        client._http.get.side_effect = [page1, page2]

        pages = list(client.paginate("act_12345/campaigns"))
        assert len(pages) == 2
        assert pages[0] == [{"id": "1"}]
        assert pages[1] == [{"id": "2"}]

    def test_empty_data_stops(self, client):
        """Should stop when data array is empty."""
        client._http.get.return_value = httpx.Response(
            200,
            json={"data": []},
            headers={},
            request=httpx.Request("GET", "https://example.com"),
        )
        pages = list(client.paginate("act_12345/campaigns"))
        assert len(pages) == 0


# ─── Convenience Method Tests ────────────────────────────


class TestConvenienceMethods:
    def test_get_campaigns_fields(self, client):
        """Should pass correct fields for campaigns."""
        client._http.get.return_value = httpx.Response(
            200,
            json={"data": [{"id": "1", "name": "Test"}]},
            headers={},
            request=httpx.Request("GET", "https://example.com"),
        )
        pages = list(client.get_campaigns())
        # Verify fields param was passed
        call_params = client._http.get.call_args.kwargs.get(
            "params", client._http.get.call_args[1].get("params", {})
        )
        assert "id" in call_params.get("fields", "")
        assert "objective" in call_params.get("fields", "")

    def test_get_insights_date_range(self, client):
        """Should pass time_range when date_start and date_stop provided."""
        client._http.get.return_value = httpx.Response(
            200,
            json={"data": [{"impressions": "100"}]},
            headers={},
            request=httpx.Request("GET", "https://example.com"),
        )
        pages = list(client.get_insights(date_start="2026-01-01", date_stop="2026-01-31"))
        call_params = client._http.get.call_args.kwargs.get(
            "params", client._http.get.call_args[1].get("params", {})
        )
        time_range = json.loads(call_params.get("time_range", "{}"))
        assert time_range["since"] == "2026-01-01"
        assert time_range["until"] == "2026-01-31"

    def test_get_insights_date_preset(self, client):
        """Should pass date_preset when provided."""
        client._http.get.return_value = httpx.Response(
            200,
            json={"data": []},
            headers={},
            request=httpx.Request("GET", "https://example.com"),
        )
        list(client.get_insights(date_preset="last_7d"))
        call_params = client._http.get.call_args.kwargs.get(
            "params", client._http.get.call_args[1].get("params", {})
        )
        assert call_params.get("date_preset") == "last_7d"

    def test_get_insights_level_param(self, client):
        """Should pass level parameter for insights."""
        client._http.get.return_value = httpx.Response(
            200,
            json={"data": []},
            headers={},
            request=httpx.Request("GET", "https://example.com"),
        )
        list(client.get_insights(level="campaign"))
        call_params = client._http.get.call_args.kwargs.get(
            "params", client._http.get.call_args[1].get("params", {})
        )
        assert call_params.get("level") == "campaign"


# ─── Context Manager Tests ───────────────────────────────


class TestContextManager:
    def test_context_manager(self, mock_exchange):
        """Should work as a context manager."""
        with MetaClient(
            ad_account_id="act_123",
            app_id="app",
            app_secret="secret",
            short_lived_token="tok",
        ) as client:
            assert client._token == "long_lived_token_abc"
        # After exit, client should be closed (no assertion needed, just no error)

    def test_static_token_context_manager(self):
        """Should work with static token as context manager."""
        with MetaClient(
            ad_account_id="act_123",
            access_token="tok",
        ) as client:
            assert client._token == "tok"
