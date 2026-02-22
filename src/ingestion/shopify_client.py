"""
Shopify GraphQL Admin API client.

Handles:
  - Authentication via client credentials grant (auto-refresh on expiry)
  - Cost-based rate limiting (leaky bucket, 1000 point max, 50 pts/sec restore)
  - Cursor-based pagination for incremental syncs
  - Retry with exponential backoff on throttle/5xx/401 errors
"""

import logging
import os
import time
from typing import Any, Generator

import httpx
from dotenv import load_dotenv

from src.ingestion.shopify_queries import API_VERSION

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

    Auth: Uses client credentials grant (SHOPIFY_CLIENT_ID + SHOPIFY_SECRET_KEY)
    to obtain short-lived access tokens that are automatically refreshed
    before each request when expired or nearing expiry.

    If an explicit access_token is passed, it is used as-is (no auto-refresh).
    """

    def __init__(
        self,
        store_url: str | None = None,
        access_token: str | None = None,
    ):
        raw_url = store_url or os.getenv("SHOPIFY_STORE_URL", "")
        self.store_domain = self._normalize_domain(raw_url)
        if not self.store_domain:
            raise ShopifyClientError(
                "No Shopify store URL configured. "
                "Set SHOPIFY_STORE_URL or pass store_url parameter."
            )

        # Token state
        self._token: str | None = None
        self._token_expires_at: float = 0.0  # epoch timestamp
        self._static_token: bool = False  # True if explicit token, no refresh

        # Client credentials for auto-refresh
        self._client_id = os.getenv("SHOPIFY_CLIENT_ID", "").strip()
        self._client_secret = os.getenv("SHOPIFY_SECRET_KEY", "").strip()

        if access_token:
            # Explicit token — use as-is, no auto-refresh
            self._token = access_token
            self._static_token = True
            logger.debug("Using explicit access token (no auto-refresh)")
        elif self._client_id and self._client_secret:
            # Obtain initial token via client credentials
            self._refresh_token()
        else:
            raise ShopifyClientError(
                "No Shopify credentials configured. "
                "Set SHOPIFY_CLIENT_ID + SHOPIFY_SECRET_KEY in .env."
            )

        self.graphql_url = (
            f"https://{self.store_domain}/admin/api/{API_VERSION}/graphql.json"
        )
        self._http = httpx.Client(
            timeout=60.0,
            headers={"Content-Type": "application/json"},
        )
        self._available_points: float = 1000.0
        self._restore_rate: float = 50.0

        logger.info(f"Shopify client initialized for {self.store_domain}")

    @staticmethod
    def _normalize_domain(url: str) -> str:
        """Extract myshopify.com domain from various URL formats."""
        url = url.strip().rstrip("/")
        if url.startswith("https://"):
            url = url[8:]
        if url.startswith("http://"):
            url = url[7:]
        # Remove any path components
        url = url.split("/")[0]
        return url

    def _refresh_token(self) -> None:
        """
        Obtain a fresh access token via client credentials grant.

        POST https://{store}/admin/oauth/access_token
        grant_type=client_credentials&client_id=...&client_secret=...

        Tokens expire in 86399 seconds (24 hours). We store the expiry
        timestamp and refresh proactively before it expires.
        """
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
                raise ShopifyClientError(
                    f"No access_token in client credentials response: {data}"
                )

            self._token = token
            self._token_expires_at = time.time() + expires_in - TOKEN_EXPIRY_BUFFER_SECONDS
            logger.info(
                f"Access token obtained, expires in {expires_in}s "
                f"(will refresh in {expires_in - TOKEN_EXPIRY_BUFFER_SECONDS}s)"
            )

        except httpx.HTTPStatusError as e:
            raise ShopifyClientError(
                f"Client credentials grant failed: {e.response.status_code} {e.response.text}"
            )
        except ShopifyClientError:
            raise
        except Exception as e:
            raise ShopifyClientError(f"Client credentials grant failed: {e}")

    def _get_token(self) -> str:
        """
        Return a valid access token, refreshing if needed.

        For static tokens (explicit access_token), returns as-is.
        For client credentials tokens, checks expiry and refreshes if stale.
        """
        if self._static_token:
            return self._token  # type: ignore

        if time.time() >= self._token_expires_at:
            logger.info("Access token expired or nearing expiry, refreshing...")
            self._refresh_token()

        return self._token  # type: ignore

    def _handle_throttle(self, extensions: dict) -> None:
        """
        Inspect the cost extensions and sleep if we're running low on points.

        GraphQL responses include:
            extensions.cost.throttleStatus.currentlyAvailable
            extensions.cost.throttleStatus.restoreRate
        """
        cost = extensions.get("cost", {})
        throttle = cost.get("throttleStatus", {})
        available = throttle.get("currentlyAvailable", self._available_points)
        restore_rate = throttle.get("restoreRate", self._restore_rate)

        self._available_points = available
        self._restore_rate = restore_rate

        if available < THROTTLE_THRESHOLD:
            wait = (THROTTLE_THRESHOLD - available) / restore_rate
            logger.info(
                f"Throttle: {available:.0f} points available, sleeping {wait:.1f}s"
            )
            time.sleep(wait)

    def execute(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Execute a GraphQL query/mutation with retry and throttle handling.

        Injects a fresh access token into each request. On 401, forces a
        token refresh and retries once before counting it as a failure.

        Returns the `data` portion of the response.
        Raises ShopifyClientError on unrecoverable errors.
        """
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        last_error: Exception | None = None
        token_refreshed_this_cycle = False

        for attempt in range(MAX_RETRIES):
            # Get a valid token for this request
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
                logger.warning(f"HTTP error (attempt {attempt + 1}): {e}, retrying in {delay}s")
                time.sleep(delay)
                continue

            # Handle 401 — token may have expired mid-sync
            if resp.status_code == 401:
                if not self._static_token and not token_refreshed_this_cycle:
                    logger.warning("Got 401 Unauthorized, refreshing access token...")
                    self._refresh_token()
                    token_refreshed_this_cycle = True
                    continue  # Retry with fresh token (don't increment backoff)
                else:
                    raise ShopifyClientError(
                        f"401 Unauthorized — access token rejected. "
                        f"Check your SHOPIFY_CLIENT_ID and SHOPIFY_SECRET_KEY."
                    )

            if resp.status_code == 429:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(f"Rate limited (429), retrying in {delay}s")
                time.sleep(delay)
                continue

            if resp.status_code >= 500:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(f"Server error ({resp.status_code}), retrying in {delay}s")
                time.sleep(delay)
                continue

            resp.raise_for_status()
            body = resp.json()

            # Handle GraphQL-level errors
            if "errors" in body:
                errors = body["errors"]
                # Check for throttle errors
                if any(
                    e.get("extensions", {}).get("code") == "THROTTLED"
                    for e in errors
                    if isinstance(e, dict)
                ):
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(f"THROTTLED error, retrying in {delay}s")
                    time.sleep(delay)
                    continue
                raise ShopifyClientError(
                    f"GraphQL errors: {errors}", errors=errors
                )

            # Handle throttle from extensions
            if "extensions" in body:
                self._handle_throttle(body["extensions"])

            return body.get("data", {})

        raise ShopifyClientError(
            f"Max retries ({MAX_RETRIES}) exceeded. Last error: {last_error}"
        )

    def paginate(
        self,
        query: str,
        resource_key: str,
        variables: dict[str, Any] | None = None,
        query_filter: str | None = None,
    ) -> Generator[list[dict], None, None]:
        """
        Auto-paginate a GraphQL query, yielding pages of nodes.

        Args:
            query: The GraphQL query with $cursor and $query variables.
            resource_key: Top-level key in data (e.g. "orders", "products").
            variables: Additional variables to pass.
            query_filter: Shopify search query string (e.g. "updated_at:>2025-01-01").

        Yields:
            Lists of node dicts (one list per page).
        """
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
        """Close the HTTP client."""
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
