"""
Shopify GraphQL Admin API client.

Handles:
  - Authentication (direct token or client credentials grant)
  - Cost-based rate limiting (leaky bucket, 1000 point max, 50 pts/sec restore)
  - Cursor-based pagination for incremental syncs
  - Retry with exponential backoff on throttle/5xx errors
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

    Auth priority:
      1. Explicit access_token parameter
      2. SHOPIFY_ACCESS_TOKEN env var
      3. Client credentials grant (SHOPIFY_CLIENT_ID + SHOPIFY_SECRET_KEY)
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

        self.access_token = access_token or self._resolve_access_token()
        if not self.access_token:
            raise ShopifyClientError(
                "No Shopify access token available. "
                "Set SHOPIFY_ACCESS_TOKEN or SHOPIFY_CLIENT_ID + SHOPIFY_SECRET_KEY."
            )

        self.graphql_url = (
            f"https://{self.store_domain}/admin/api/{API_VERSION}/graphql.json"
        )
        self._http = httpx.Client(
            timeout=60.0,
            headers={
                "Content-Type": "application/json",
                "X-Shopify-Access-Token": self.access_token,
            },
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

    def _resolve_access_token(self) -> str | None:
        """Resolve access token: env var first, then client credentials grant."""
        token = os.getenv("SHOPIFY_ACCESS_TOKEN", "").strip()
        if token:
            logger.debug("Using SHOPIFY_ACCESS_TOKEN from env")
            return token

        # Try client credentials grant
        client_id = os.getenv("SHOPIFY_CLIENT_ID", "").strip()
        client_secret = os.getenv("SHOPIFY_SECRET_KEY", "").strip()
        if client_id and client_secret:
            return self._obtain_token_via_client_credentials(client_id, client_secret)

        return None

    def _obtain_token_via_client_credentials(
        self, client_id: str, client_secret: str
    ) -> str | None:
        """
        Exchange client credentials for an access token.

        POST https://{store}/admin/oauth/access_token
        grant_type=client_credentials&client_id=...&client_secret=...
        """
        url = f"https://{self.store_domain}/admin/oauth/access_token"
        logger.info(f"Obtaining access token via client credentials for {self.store_domain}")

        try:
            resp = httpx.post(
                url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            token = data.get("access_token")
            if token:
                logger.info("Access token obtained via client credentials")
                return token
            logger.error(f"No access_token in response: {data}")
            return None
        except httpx.HTTPStatusError as e:
            logger.error(f"Client credentials grant failed: {e.response.status_code} {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Client credentials grant failed: {e}")
            return None

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

        Returns the `data` portion of the response.
        Raises ShopifyClientError on unrecoverable errors.
        """
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                resp = self._http.post(self.graphql_url, json=payload)
            except httpx.HTTPError as e:
                last_error = e
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(f"HTTP error (attempt {attempt + 1}): {e}, retrying in {delay}s")
                time.sleep(delay)
                continue

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
