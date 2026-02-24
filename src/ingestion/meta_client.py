"""
Meta Marketing API client.

Handles:
  - Token exchange: short-lived → long-lived token (auto-refresh 7 days before expiry)
  - Cursor-based pagination (Meta uses `after` cursors in `paging.cursors`)
  - Rate limiting via x-app-usage header (back off when any metric > 75%)
  - Retry with exponential backoff on rate-limit (17), expired token (190), transient errors
  - Fetching campaigns, ad_sets, ads, and ads_insights for an ad account

API version: v25.0
Base URL: https://graph.facebook.com/v25.0
"""

import json
import logging
import os
import time
from typing import Any, Generator

import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

API_VERSION = "v25.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"

MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0  # seconds

# Back off when any x-app-usage metric exceeds this %
USAGE_THRESHOLD = 75

# Refresh long-lived token 7 days before it expires
TOKEN_REFRESH_BUFFER_SECONDS = 7 * 24 * 3600  # 7 days


class MetaClientError(Exception):
    """Raised for Meta API errors."""

    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


class MetaRateLimitError(MetaClientError):
    """Raised when the API returns a rate-limit error (code 17 or 4)."""
    pass


class MetaTokenExpiredError(MetaClientError):
    """Raised when the access token is expired or invalid (code 190)."""
    pass


class MetaClient:
    """
    Synchronous REST client for the Meta Marketing API.

    Auth: Exchanges a short-lived user token for a long-lived token (~60 days),
    stored in memory. Auto-refreshes 7 days before expiry.

    Usage:
        with MetaClient(ad_account_id="act_123456") as client:
            for page in client.paginate_insights(date_preset="last_7d"):
                process(page)
    """

    def __init__(
        self,
        ad_account_id: str | None = None,
        access_token: str | None = None,
        app_id: str | None = None,
        app_secret: str | None = None,
        short_lived_token: str | None = None,
    ):
        self.ad_account_id = ad_account_id or os.getenv("META_AD_ACCOUNT_ID", "")
        if not self.ad_account_id:
            raise MetaClientError(
                "No Meta ad account ID configured. "
                "Set META_AD_ACCOUNT_ID or pass ad_account_id parameter."
            )
        # Ensure act_ prefix
        if not self.ad_account_id.startswith("act_"):
            self.ad_account_id = f"act_{self.ad_account_id}"

        self._app_id = app_id or os.getenv("META_APP_ID", "").strip()
        self._app_secret = app_secret or os.getenv("META_APP_SECRET", "").strip()

        # Token state
        self._token: str | None = None
        self._token_expires_at: float = 0.0  # epoch timestamp
        self._static_token: bool = False

        if access_token:
            # Explicit long-lived token — use as-is
            self._token = access_token
            self._static_token = True
            logger.debug("Using explicit access token (no auto-refresh)")
        else:
            short_token = (
                short_lived_token
                or os.getenv("META_SHORT_LIVED_TOKEN", "").strip()
            )
            if short_token and self._app_id and self._app_secret:
                self._exchange_token(short_token)
            elif short_token:
                # Have a token but no app credentials for exchange — use as-is
                self._token = short_token
                self._static_token = True
                logger.warning(
                    "META_APP_ID/META_APP_SECRET not set — "
                    "using short-lived token without exchange"
                )
            else:
                raise MetaClientError(
                    "No Meta credentials configured. "
                    "Set META_SHORT_LIVED_TOKEN + META_APP_ID + META_APP_SECRET in .env."
                )

        self._http = httpx.Client(timeout=60.0)
        logger.info(f"Meta client initialized for {self.ad_account_id}")

    def _exchange_token(self, short_token: str) -> None:
        """
        Exchange a short-lived user token for a long-lived token.

        GET /oauth/access_token?grant_type=fb_exchange_token
            &client_id={app_id}&client_secret={app_secret}
            &fb_exchange_token={short_token}

        Returns a ~60-day token.
        """
        url = f"{BASE_URL}/oauth/access_token"
        logger.info("Exchanging short-lived token for long-lived token...")

        try:
            resp = httpx.get(
                url,
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": self._app_id,
                    "client_secret": self._app_secret,
                    "fb_exchange_token": short_token,
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()

            token = data.get("access_token")
            expires_in = data.get("expires_in", 5184000)  # default 60 days

            if not token:
                raise MetaClientError(
                    f"No access_token in token exchange response: {data}"
                )

            self._token = token
            self._token_expires_at = time.time() + expires_in - TOKEN_REFRESH_BUFFER_SECONDS
            logger.info(
                f"Long-lived token obtained, expires in {expires_in // 86400} days "
                f"(will refresh in {(expires_in - TOKEN_REFRESH_BUFFER_SECONDS) // 86400} days)"
            )

        except httpx.HTTPStatusError as e:
            raise MetaClientError(
                f"Token exchange failed: {e.response.status_code} {e.response.text}"
            )
        except MetaClientError:
            raise
        except Exception as e:
            raise MetaClientError(f"Token exchange failed: {e}")

    def _refresh_token_if_needed(self) -> None:
        """Refresh the long-lived token if it's nearing expiry."""
        if self._static_token:
            return
        if time.time() >= self._token_expires_at and self._token:
            logger.info("Long-lived token nearing expiry, refreshing...")
            # Long-lived tokens can be refreshed by exchanging themselves
            self._exchange_token(self._token)

    def _get_token(self) -> str:
        """Return a valid access token, refreshing if needed."""
        self._refresh_token_if_needed()
        if not self._token:
            raise MetaClientError("No access token available")
        return self._token

    def _check_rate_limit(self, response: httpx.Response) -> None:
        """
        Check x-app-usage header and sleep if usage is high.

        Header value is JSON: {"call_count": N, "total_cputime": N, "total_time": N}
        All values are percentages (0-100). Back off when any > 75%.
        """
        usage_header = response.headers.get("x-app-usage")
        if not usage_header:
            return

        try:
            usage = json.loads(usage_header)
        except (json.JSONDecodeError, TypeError):
            return

        call_count = usage.get("call_count", 0)
        cpu_time = usage.get("total_cputime", 0)
        total_time = usage.get("total_time", 0)
        max_usage = max(call_count, cpu_time, total_time)

        if max_usage > USAGE_THRESHOLD:
            # Proportional backoff: higher usage = longer wait
            wait = min(60, max(5, (max_usage - USAGE_THRESHOLD) * 2))
            logger.warning(
                f"Rate limit approaching: call_count={call_count}%, "
                f"cpu={cpu_time}%, time={total_time}%. Sleeping {wait}s"
            )
            time.sleep(wait)

    def _handle_error_response(self, resp: httpx.Response) -> None:
        """Parse Meta API error response and raise appropriate exception."""
        try:
            body = resp.json()
            error = body.get("error", {})
            code = error.get("code")
            message = error.get("message", resp.text)
        except Exception:
            code = None
            message = resp.text

        if code in (17, 4):
            raise MetaRateLimitError(
                f"Rate limited (code {code}): {message}", code=code
            )
        if code == 190:
            raise MetaTokenExpiredError(
                f"Token expired (code {code}): {message}", code=code
            )
        raise MetaClientError(
            f"Meta API error {resp.status_code} (code {code}): {message}",
            code=code,
        )

    def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Make a GET request to the Meta Graph API with retry logic.

        Args:
            endpoint: API path (e.g. "act_123/campaigns" or full URL).
            params: Query parameters.

        Returns the parsed JSON response body.
        """
        if endpoint.startswith("http"):
            url = endpoint
        else:
            url = f"{BASE_URL}/{endpoint}"

        params = dict(params or {})
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES):
            token = self._get_token()
            params["access_token"] = token

            try:
                resp = self._http.get(url, params=params)
            except httpx.HTTPError as e:
                last_error = e
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    f"HTTP error (attempt {attempt + 1}): {e}, retrying in {delay}s"
                )
                time.sleep(delay)
                continue

            # Check rate limits on every response
            self._check_rate_limit(resp)

            if resp.status_code == 200:
                return resp.json()

            # Handle errors
            try:
                self._handle_error_response(resp)
            except MetaRateLimitError as e:
                last_error = e
                delay = RETRY_BASE_DELAY * (2 ** attempt) * 5  # longer backoff for rate limits
                logger.warning(f"Rate limited, retrying in {delay}s")
                time.sleep(delay)
                continue
            except MetaTokenExpiredError as e:
                if not self._static_token and attempt == 0:
                    logger.warning("Token expired, attempting refresh...")
                    self._exchange_token(self._token or "")
                    continue
                raise
            except MetaClientError:
                raise

        raise MetaClientError(
            f"Max retries ({MAX_RETRIES}) exceeded. Last error: {last_error}"
        )

    def paginate(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> Generator[list[dict], None, None]:
        """
        Auto-paginate a Meta API endpoint, yielding pages of records.

        Meta uses cursor-based pagination with `paging.cursors.after` and
        `paging.next` URL.

        Yields lists of dicts (one list per page).
        """
        params = dict(params or {})
        page_num = 0

        while True:
            data = self.get(endpoint, params=params)
            records = data.get("data", [])

            if not records:
                break

            page_num += 1
            logger.debug(f"Page {page_num}: {len(records)} records from {endpoint}")
            yield records

            # Check for next page
            paging = data.get("paging", {})
            next_url = paging.get("next")
            if not next_url:
                break

            # Use the full next URL directly (includes cursor params)
            endpoint = next_url
            params = {}  # next URL already has all params

    # ─── Convenience methods for Meta Ads resources ──────────

    # Field lists match the DB table columns from seed.py DDL

    CAMPAIGN_FIELDS = (
        "id,account_id,name,status,effective_status,configured_status,"
        "objective,buying_type,bid_strategy,daily_budget,lifetime_budget,"
        "budget_remaining,spend_cap,start_time,stop_time,created_time,"
        "updated_time,special_ad_category,special_ad_category_country,"
        "adlabels,issues_info"
    )

    AD_SET_FIELDS = (
        "id,account_id,campaign_id,name,effective_status,daily_budget,"
        "lifetime_budget,budget_remaining,bid_strategy,bid_amount,"
        "bid_constraints,bid_info,start_time,end_time,created_time,"
        "updated_time,targeting,promoted_object,adlabels,learning_stage_info"
    )

    AD_FIELDS = (
        "id,account_id,campaign_id,adset_id,name,status,effective_status,"
        "bid_type,bid_amount,bid_info,creative,created_time,updated_time,"
        "last_updated_by_app_id,source_ad_id,targeting,tracking_specs,"
        "conversion_specs,adlabels,recommendations"
    )

    INSIGHT_FIELDS = (
        "date_start,date_stop,account_id,account_name,account_currency,"
        "campaign_id,campaign_name,adset_id,adset_name,ad_id,ad_name,"
        "objective,optimization_goal,buying_type,attribution_setting,"
        "impressions,clicks,spend,reach,frequency,cpc,cpm,cpp,ctr,"
        "unique_clicks,unique_ctr,cost_per_unique_click,inline_link_clicks,"
        "inline_link_click_ctr,inline_post_engagement,"
        "cost_per_inline_link_click,cost_per_inline_post_engagement,"
        "social_spend,quality_ranking,engagement_rate_ranking,"
        "conversion_rate_ranking,actions,action_values,conversions,"
        "conversion_values,cost_per_action_type,cost_per_conversion,"
        "purchase_roas,website_purchase_roas,outbound_clicks"
    )

    def get_campaigns(self, limit: int = 500) -> Generator[list[dict], None, None]:
        """Fetch all campaigns for the ad account."""
        return self.paginate(
            f"{self.ad_account_id}/campaigns",
            params={"fields": self.CAMPAIGN_FIELDS, "limit": limit},
        )

    def get_ad_sets(self, limit: int = 500) -> Generator[list[dict], None, None]:
        """Fetch all ad sets for the ad account."""
        return self.paginate(
            f"{self.ad_account_id}/adsets",
            params={"fields": self.AD_SET_FIELDS, "limit": limit},
        )

    def get_ads(self, limit: int = 500) -> Generator[list[dict], None, None]:
        """Fetch all ads for the ad account."""
        return self.paginate(
            f"{self.ad_account_id}/ads",
            params={"fields": self.AD_FIELDS, "limit": limit},
        )

    def get_insights(
        self,
        date_start: str | None = None,
        date_stop: str | None = None,
        date_preset: str | None = None,
        level: str = "ad",
        limit: int = 500,
    ) -> Generator[list[dict], None, None]:
        """
        Fetch ads insights for the ad account.

        Args:
            date_start: Start date (YYYY-MM-DD). Used with date_stop.
            date_stop: End date (YYYY-MM-DD). Used with date_start.
            date_preset: Meta date preset (e.g. "last_7d", "last_30d").
            level: Aggregation level: "ad", "adset", "campaign", "account".
            limit: Page size.

        Yields lists of insight dicts (one list per page).
        """
        params: dict[str, Any] = {
            "fields": self.INSIGHT_FIELDS,
            "level": level,
            "limit": limit,
        }

        if date_start and date_stop:
            params["time_range"] = json.dumps(
                {"since": date_start, "until": date_stop}
            )
        elif date_preset:
            params["date_preset"] = date_preset

        return self.paginate(
            f"{self.ad_account_id}/insights",
            params=params,
        )

    def close(self) -> None:
        """Close the HTTP client."""
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
