"""
Shopify GraphQL Admin API client.

Handles:
  - Authentication via OAuth access tokens (DB-backed) or client credentials (legacy/env)
  - Cost-based rate limiting (leaky bucket, 1000 point max, 50 pts/sec restore)
  - Cursor-based pagination for incremental syncs
  - Retry with exponential backoff on throttle/5xx/401 errors
"""

import logging
import os
import time
from typing import Any, Generator

import httpx
import psycopg2
from dotenv import load_dotenv

from src.ingestion.shopify_queries import API_VERSION
from src.auth.encryption import decrypt_token

logger = logging.getLogger(__name__)

load_dotenv()

# Throttle safety margin — start backing off when below this many points
THROTTLE_THRESHOLD = 100
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0  # seconds

# Refresh the token 5 minutes before it actually expires
TOKEN_EXPIRY_BUFFER_SECONDS = 300


class ShopifyClientError(Exception):
    """Raised for Shopify API errors."""

    def __init__(self, message: str, errors: list | None = None):
        super().__init__(message)
        self.errors = errors or []


class ShopifyThrottledError(ShopifyClientError):
    """Raised when the API returns a THROTTLED error."""
    pass


class ShopifyClient:
    """
    Synchronous GraphQL client for the Shopify Admin API.

    Auth modes:
    1. Tenant DB Mode (Recommended): Pass `tenant_id` + `conn`. Fetches encrypted token from DB.
    2. Static Token Mode: Pass `access_token` + `store_url`. Uses token as-is.
    3. Legacy Env Mode: Pass nothing. Reads SHOPIFY_CLIENT_ID/_SECRET from env.
    """

    def __init__(
        self,
        tenant_id: int | None = None,
        conn = None,
        store_url: str | None = None,
        access_token: str | None = None,
    ):
        self.tenant_id = tenant_id
        self.conn = conn
        
        # Token state
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._static_token: bool = False

        # Normalize store_url from arg or env to allow static token mode to use env URL
        raw_url = store_url or os.getenv("SHOPIFY_STORE_URL", "")
        self.store_domain = self._normalize_domain(raw_url)

        # 1. Tenant DB Mode
        if self.tenant_id and self.conn:
            self._load_from_db()
        # 2. Static Token Mode
        elif access_token:
            if not self.store_domain:
                raise ShopifyClientError("No Shopify store URL configured")
            self._token = access_token
            self._static_token = True
            logger.debug(f"Using static access token for {self.store_domain}")
        # 3. Legacy Env Mode
        else:
            self._client_id = os.getenv("SHOPIFY_CLIENT_ID", "").strip()
            self._client_secret = os.getenv("SHOPIFY_SECRET_KEY", "").strip()
            
            if not self.store_domain:
                raise ShopifyClientError("No Shopify store URL configured")
            
            if self._client_id and self._client_secret:
                self._refresh_legacy_token()
            else:
                raise ShopifyClientError("No Shopify credentials configured")

        self.graphql_url = (
            f"https://{self.store_domain}/admin/api/{API_VERSION}/graphql.json"
        )
        self._http = httpx.Client(
            timeout=60.0,
            headers={"Content-Type": "application/json"},
        )
        self._available_points: float = 1000.0
        self._restore_rate: float = 50.0

    def _load_from_db(self):
        """Fetch store URL and encrypted token from database."""
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT shopify_store_url, shopify_access_token FROM public.tenants WHERE id = %s",
                (self.tenant_id,)
            )
            row = cur.fetchone()
            if not row:
                raise ShopifyClientError(f"Tenant {self.tenant_id} not found")
            
            url, encrypted_token = row
            if not url or not encrypted_token:
                raise ShopifyClientError(f"Tenant {self.tenant_id} not connected to Shopify")
            
            self.store_domain = self._normalize_domain(url)
            self._token = decrypt_token(encrypted_token)
            self._static_token = True  # OAuth tokens are permanent
            logger.info(f"Loaded Shopify credentials for tenant {self.tenant_id} ({self.store_domain})")

    @staticmethod
    def _normalize_domain(url: str) -> str:
        """Extract myshopify.com domain from various URL formats."""
        url = url.strip().rstrip("/")
        if url.startswith("https://"):
            url = url[8:]
        if url.startswith("http://"):
            url = url[7:]
        url = url.split("/")[0]
        return url

    def _refresh_legacy_token(self) -> None:
        """Legacy client credentials flow."""
        url = f"https://{self.store_domain}/admin/oauth/access_token"
        logger.info(f"Obtaining access token via client credentials for {self.store_domain}")

        try:
            resp = httpx.post(
                url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            token = data.get("access_token")
            expires_in = data.get("expires_in", 86399)

            if not token:
                raise ShopifyClientError(f"No access_token in response: {data}")

            self._token = token
            self._token_expires_at = time.time() + expires_in - TOKEN_EXPIRY_BUFFER_SECONDS

        except Exception as e:
            raise ShopifyClientError(f"Client credentials grant failed: {e}")

    def _get_token(self) -> str:
        """Return a valid access token."""
        if self._static_token:
            if not self._token:
                raise ShopifyClientError("No access token available")
            return self._token

        if time.time() >= self._token_expires_at:
            logger.info("Legacy token expired, refreshing...")
            self._refresh_legacy_token()

        if not self._token:
            raise ShopifyClientError("No access token available")
        return self._token

    def _handle_throttle(self, extensions: dict) -> None:
        """Inspect cost and sleep if needed."""
        cost = extensions.get("cost", {})
        throttle = cost.get("throttleStatus", {})
        available = throttle.get("currentlyAvailable", self._available_points)
        restore_rate = throttle.get("restoreRate", self._restore_rate)

        self._available_points = available
        self._restore_rate = restore_rate

        if available < THROTTLE_THRESHOLD:
            wait = (THROTTLE_THRESHOLD - available) / restore_rate
            logger.info(f"Throttle: {available:.0f} points available, sleeping {wait:.1f}s")
            time.sleep(wait)

    def execute(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a GraphQL query/mutation with retry and throttle handling."""
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        last_error: Exception | None = None
        token_refreshed_this_cycle = False

        for attempt in range(MAX_RETRIES):
            token = self._get_token()

            try:
                resp = self._http.post(
                    self.graphql_url,
                    json=payload,
                    headers={"X-Shopify-Access-Token": token},
                )
            except httpx.HTTPError as e:
                last_error = e
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(f"HTTP error: {e}, retrying in {delay}s")
                time.sleep(delay)
                continue

            if resp.status_code == 401:
                # If DB backed, maybe token was revoked. 
                # If legacy, maybe expired.
                if not self._static_token and not token_refreshed_this_cycle:
                    logger.warning("401 Unauthorized, refreshing legacy token...")
                    self._refresh_legacy_token()
                    token_refreshed_this_cycle = True
                    continue
                else:
                    raise ShopifyClientError("401 Unauthorized — Access token rejected/revoked.")

            if resp.status_code in (429, 500, 502, 503, 504):
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(f"Error {resp.status_code}, retrying in {delay}s")
                time.sleep(delay)
                continue

            resp.raise_for_status()
            body = resp.json()

            if "errors" in body:
                errors = body["errors"]
                if any(e.get("extensions", {}).get("code") == "THROTTLED" for e in errors):
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(f"THROTTLED error, retrying in {delay}s")
                    time.sleep(delay)
                    continue
                raise ShopifyClientError(f"GraphQL errors: {errors}", errors=errors)

            if "extensions" in body:
                self._handle_throttle(body["extensions"])

            return body.get("data", {})

        raise ShopifyClientError(f"Max retries ({MAX_RETRIES}) exceeded. Last error: {last_error}")

    def paginate(
        self,
        query: str,
        resource_key: str,
        variables: dict[str, Any] | None = None,
        query_filter: str | None = None,
    ) -> Generator[list[dict], None, None]:
        """Auto-paginate a GraphQL query."""
        cursor: str | None = None
        page = 0
        vars_ = dict(variables or {})

        if query_filter:
            vars_["query"] = query_filter

        while True:
            vars_["cursor"] = cursor
            data = self.execute(query, variables=vars_)
            connection = data.get(resource_key, {})
            edges = connection.get("edges", [])

            if not edges:
                break

            nodes = [edge["node"] for edge in edges]
            page += 1
            logger.debug(f"Page {page}: {len(nodes)} {resource_key}")
            yield nodes

            page_info = connection.get("pageInfo", {})
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")

    def close(self) -> None:
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
