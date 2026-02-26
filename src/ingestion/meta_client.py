"""
Meta Marketing API client.

Handles:
  - Token exchange: short-lived → long-lived token (auto-refresh 7 days before expiry)
  - DB-backed token storage and retrieval (per-tenant)
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
from datetime import datetime, timedelta
from typing import Any, Generator

import httpx
import psycopg2
from dotenv import load_dotenv

from src.auth.encryption import encrypt_token, decrypt_token

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

    Auth modes:
    1. Tenant DB Mode: Pass `tenant_id` + `conn`. Fetches encrypted token from DB.
    2. Static Token Mode: Pass `access_token` + `ad_account_id`.
    3. Legacy Env Mode: Pass nothing. Reads from env.
    """

    def __init__(
        self,
        tenant_id: int | None = None,
        conn = None,
        ad_account_id: str | None = None,
        access_token: str | None = None,
        app_id: str | None = None,
        app_secret: str | None = None,
        short_lived_token: str | None = None,
    ):
        self.tenant_id = tenant_id
        self.conn = conn
        # Prefer connector app credentials (Marketing API) over social login app
        self._app_id = app_id or os.getenv("META_CONNECTOR_APP_ID", "").strip() or os.getenv("META_APP_ID", "").strip()
        self._app_secret = app_secret or os.getenv("META_CONNECTOR_APP_SECRET", "").strip() or os.getenv("META_APP_SECRET", "").strip()

        # Token state
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._static_token: bool = False

        self.ad_account_id = ""

        # 1. Tenant DB Mode
        if self.tenant_id and self.conn:
            self._load_from_db()
        # 2. Static Token Mode
        elif access_token and ad_account_id:
            self.ad_account_id = self._normalize_account_id(ad_account_id)
            self._token = access_token
            self._static_token = True
            logger.debug("Using explicit access token (no auto-refresh)")
        # 3. Legacy Env Mode
        else:
            self.ad_account_id = self._normalize_account_id(
                ad_account_id or os.getenv("META_AD_ACCOUNT_ID", "")
            )
            if not self.ad_account_id:
                raise MetaClientError("No Meta ad account ID configured")

            short_token = short_lived_token or os.getenv("META_SHORT_LIVED_TOKEN", "").strip()
            
            if short_token and self._app_id and self._app_secret:
                self._token, expires_in = self._exchange_token(short_token)
                self._token_expires_at = time.time() + expires_in - TOKEN_REFRESH_BUFFER_SECONDS
            elif short_token:
                self._token = short_token
                self._static_token = True
                logger.warning("META_APP_ID/SECRET not set — using short-lived token without exchange")
            else:
                raise MetaClientError("No Meta credentials configured")

        self._http = httpx.Client(timeout=60.0)
        logger.info(f"Meta client initialized for {self.ad_account_id}")

    @staticmethod
    def _normalize_account_id(acc_id: str) -> str:
        if not acc_id:
            return ""
        if not acc_id.startswith("act_"):
            return f"act_{acc_id}"
        return acc_id

    def _load_from_db(self):
        """Fetch credentials from database."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT meta_account_id, meta_access_token, meta_token_expires_at 
                FROM public.tenants WHERE id = %s
                """,
                (self.tenant_id,)
            )
            row = cur.fetchone()
            if not row:
                raise MetaClientError(f"Tenant {self.tenant_id} not found")
            
            acc_id, encrypted_token, expires_at = row
            if not acc_id or not encrypted_token:
                raise MetaClientError(f"Tenant {self.tenant_id} not connected to Meta")
            
            self.ad_account_id = self._normalize_account_id(acc_id)
            self._token = decrypt_token(encrypted_token)
            
            if expires_at:
                # Convert DB timestamp to unix epoch
                self._token_expires_at = expires_at.timestamp()
            else:
                # Fallback if expiry not tracked
                self._token_expires_at = time.time() + 86400 * 60

    def _exchange_token(self, short_token: str) -> tuple[str, int]:
        """Exchange token for long-lived one. Returns (token, expires_in)."""
        url = f"{BASE_URL}/oauth/access_token"
        logger.info("Exchanging/refreshing Meta token...")

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
                raise MetaClientError(f"No access_token in response: {data}")

            return token, expires_in

        except Exception as e:
            raise MetaClientError(f"Token exchange failed: {e}")

    def _update_db_token(self, token: str, expires_in: int):
        """Update refreshed token in database."""
        encrypted = encrypt_token(token)
        expires_at = datetime.now() + timedelta(seconds=expires_in)
        
        # We need a new cursor transaction here
        # Assuming self.conn is an open psycopg2 connection
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE public.tenants 
                    SET meta_access_token = %s,
                        meta_token_expires_at = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (encrypted, expires_at, self.tenant_id)
                )
            self.conn.commit()
            logger.info(f"Updated Meta token for tenant {self.tenant_id} in DB")
        except Exception as e:
            logger.error(f"Failed to update Meta token in DB: {e}")
            self.conn.rollback()

    def _get_token(self) -> str:
        """Return a valid access token, refreshing if needed."""
        if self._static_token:
            if not self._token:
                raise MetaClientError("No access token available")
            return self._token

        # Check expiry
        if time.time() >= self._token_expires_at - TOKEN_REFRESH_BUFFER_SECONDS:
            if self._token and self._app_id and self._app_secret:
                logger.info("Long-lived token nearing expiry, refreshing...")
                new_token, expires_in = self._exchange_token(self._token)
                
                self._token = new_token
                self._token_expires_at = time.time() + expires_in
                
                if self.tenant_id and self.conn:
                    self._update_db_token(new_token, expires_in)
            else:
                logger.warning("Cannot refresh token: missing app credentials or current token")

        if not self._token:
            raise MetaClientError("No access token available")
        return self._token

    def _check_rate_limit(self, response: httpx.Response) -> None:
        """Check x-app-usage header and sleep if usage is high."""
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
            wait = min(60, max(5, (max_usage - USAGE_THRESHOLD) * 2))
            logger.warning(f"Rate limit approaching: {max_usage}%. Sleeping {wait}s")
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
            raise MetaRateLimitError(f"Rate limited (code {code}): {message}", code=code)
        if code == 190:
            raise MetaTokenExpiredError(f"Token expired (code {code}): {message}", code=code)
        raise MetaClientError(f"Meta API error {resp.status_code} (code {code}): {message}", code=code)

    def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a GET request to the Meta Graph API with retry logic."""
        if endpoint.startswith("http"):
            url = endpoint
        else:
            url = f"{BASE_URL}/{endpoint}"

        params = dict(params or {})
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                token = self._get_token()
            except MetaClientError as e:
                # If getting token fails (e.g. refresh failed), raise immediately
                raise e

            params["access_token"] = token

            try:
                resp = self._http.get(url, params=params)
            except httpx.HTTPError as e:
                last_error = e
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(f"HTTP error: {e}, retrying in {delay}s")
                time.sleep(delay)
                continue

            self._check_rate_limit(resp)

            if resp.status_code == 200:
                return resp.json()

            try:
                self._handle_error_response(resp)
            except MetaRateLimitError as e:
                last_error = e
                delay = RETRY_BASE_DELAY * (2 ** attempt) * 5
                logger.warning(f"Rate limited, retrying in {delay}s")
                time.sleep(delay)
                continue
            except MetaTokenExpiredError as e:
                # If we have credentials, try to refresh once
                if self._app_id and self._app_secret and attempt == 0:
                    logger.warning("Token expired (190), attempting refresh...")
                    try:
                        new_token, expires_in = self._exchange_token(self._token or "")
                        self._token = new_token
                        self._token_expires_at = time.time() + expires_in
                        if self.tenant_id and self.conn:
                            self._update_db_token(new_token, expires_in)
                        continue
                    except Exception as refresh_err:
                        logger.error(f"Refresh failed: {refresh_err}")
                        raise e
                raise
            except MetaClientError:
                raise

        raise MetaClientError(f"Max retries ({MAX_RETRIES}) exceeded. Last error: {last_error}")

    def paginate(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> Generator[list[dict], None, None]:
        """Auto-paginate a Meta API endpoint."""
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

            paging = data.get("paging", {})
            next_url = paging.get("next")
            if not next_url:
                break

            endpoint = next_url
            params = {}

    # ─── Convenience methods ──────────

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
        return self.paginate(
            f"{self.ad_account_id}/campaigns",
            params={"fields": self.CAMPAIGN_FIELDS, "limit": limit},
        )

    def get_ad_sets(self, limit: int = 500) -> Generator[list[dict], None, None]:
        return self.paginate(
            f"{self.ad_account_id}/adsets",
            params={"fields": self.AD_SET_FIELDS, "limit": limit},
        )

    def get_ads(self, limit: int = 500) -> Generator[list[dict], None, None]:
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
        params: dict[str, Any] = {
            "fields": self.INSIGHT_FIELDS,
            "level": level,
            "limit": limit,
        }

        if date_start and date_stop:
            params["time_range"] = json.dumps({"since": date_start, "until": date_stop})
        elif date_preset:
            params["date_preset"] = date_preset

        return self.paginate(f"{self.ad_account_id}/insights", params=params)

    def close(self) -> None:
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
