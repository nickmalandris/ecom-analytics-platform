"""
Shopify Bulk Operations API client.

Handles the full lifecycle:
  1. Submit a bulkOperationRunQuery mutation
  2. Poll for completion
  3. Download the JSONL result file
  4. Stream-parse the JSONL with __parentId reassembly
"""

import json
import logging
import tempfile
import time
from pathlib import Path
from typing import Any, Generator

import httpx

from src.ingestion.shopify_client import ShopifyClient, ShopifyClientError
from src.ingestion.shopify_queries import (
    BULK_OPERATION_CANCEL,
    BULK_OPERATION_POLL,
    BULK_OPERATION_RUN,
)

logger = logging.getLogger(__name__)

# Poll interval and limits
POLL_INTERVAL_SECONDS = 5
POLL_MAX_WAIT_SECONDS = 3600  # 1 hour max wait
COMPLETED_STATUSES = {"COMPLETED", "FAILED", "CANCELED", "CANCELLED"}


class BulkOperationError(ShopifyClientError):
    """Raised when a bulk operation fails."""
    pass


class ShopifyBulkClient:
    """
    Client for Shopify Bulk Operations.

    Uses an existing ShopifyClient for GraphQL execution.
    """

    def __init__(self, client: ShopifyClient):
        self.client = client

    def run_bulk_query(
        self,
        query: str,
        query_filter: str = "",
    ) -> str:
        """
        Submit a bulk operation and return the operation GID.

        Args:
            query: The bulk query template (from shopify_queries.py).
            query_filter: Optional filter to replace QUERY_FILTER placeholder.

        Returns:
            The bulk operation GID (e.g. "gid://shopify/BulkOperation/123").
        """
        # Replace the filter placeholder
        resolved_query = query.replace("QUERY_FILTER", query_filter)

        data = self.client.execute(
            BULK_OPERATION_RUN,
            variables={"query": resolved_query},
        )

        result = data.get("bulkOperationRunQuery", {})
        user_errors = result.get("userErrors", [])
        if user_errors:
            raise BulkOperationError(
                f"Bulk operation failed to start: {user_errors}",
                errors=user_errors,
            )

        op = result.get("bulkOperation", {})
        op_id = op.get("id")
        status = op.get("status")

        if not op_id:
            raise BulkOperationError("No bulk operation ID returned")

        logger.info(f"Bulk operation submitted: {op_id} status={status}")
        return op_id

    def poll_until_complete(self, operation_id: str) -> dict:
        """
        Poll a bulk operation until it finishes.

        Returns the final operation dict with url, status, objectCount, etc.
        Raises BulkOperationError if the operation fails or times out.
        """
        start = time.time()

        while True:
            elapsed = time.time() - start
            if elapsed > POLL_MAX_WAIT_SECONDS:
                # Try to cancel the stuck operation
                self._cancel_operation(operation_id)
                raise BulkOperationError(
                    f"Bulk operation timed out after {elapsed:.0f}s: {operation_id}"
                )

            data = self.client.execute(
                BULK_OPERATION_POLL,
                variables={"id": operation_id},
            )
            op = data.get("node", {})
            status = op.get("status", "UNKNOWN")
            object_count = op.get("objectCount", "?")

            logger.debug(
                f"Bulk op {operation_id}: status={status} objects={object_count} "
                f"elapsed={elapsed:.0f}s"
            )

            if status == "COMPLETED":
                logger.info(
                    f"Bulk operation completed: {object_count} objects, "
                    f"{op.get('fileSize', '?')} bytes, {elapsed:.0f}s"
                )
                return op

            if status in ("FAILED", "CANCELED", "CANCELLED"):
                error_code = op.get("errorCode", "UNKNOWN")
                partial_url = op.get("partialDataUrl")
                msg = f"Bulk operation {status}: errorCode={error_code}"
                if partial_url:
                    msg += f" (partial data available at {partial_url})"
                raise BulkOperationError(msg)

            time.sleep(POLL_INTERVAL_SECONDS)

    def download_jsonl(self, url: str) -> Path:
        """
        Download the JSONL result file to a temp location.

        Returns the path to the downloaded file.
        """
        logger.info(f"Downloading JSONL from bulk operation...")

        tmp = tempfile.NamedTemporaryFile(
            suffix=".jsonl", prefix="shopify_bulk_", delete=False
        )
        tmp_path = Path(tmp.name)

        with httpx.stream("GET", url, timeout=300.0) as resp:
            resp.raise_for_status()
            total_bytes = 0
            for chunk in resp.iter_bytes(chunk_size=65536):
                tmp.write(chunk)
                total_bytes += len(chunk)

        tmp.close()
        logger.info(f"Downloaded {total_bytes:,} bytes to {tmp_path}")
        return tmp_path

    @staticmethod
    def stream_jsonl(path: Path) -> Generator[dict, None, None]:
        """
        Stream-parse a JSONL file line by line.

        Yields raw dicts (one per line). Each dict may have an `__parentId`
        field linking it to its parent record.
        """
        with open(path, "r") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as e:
                    logger.warning(f"Skipping malformed JSONL line {line_num}: {e}")

    @staticmethod
    def reassemble_with_children(
        jsonl_path: Path,
        parent_type: str,
        child_configs: list[dict],
    ) -> Generator[dict, None, None]:
        """
        Reassemble parent-child relationships from flat JSONL.

        In Shopify bulk JSONL, parents and children are interleaved:
            {"id": "gid://shopify/Product/1", ...}
            {"id": "gid://shopify/ProductVariant/10", "__parentId": "gid://shopify/Product/1", ...}
            {"id": "gid://shopify/ProductVariant/11", "__parentId": "gid://shopify/Product/1", ...}
            {"id": "gid://shopify/Product/2", ...}

        This function collects children and attaches them to the parent
        before yielding the complete parent record.

        Args:
            jsonl_path: Path to the JSONL file.
            parent_type: GID type prefix for parent (e.g. "Product").
            child_configs: List of dicts with:
                - "type": GID type prefix (e.g. "ProductVariant")
                - "field": field name to attach children to on parent (e.g. "variants")

        Yields:
            Parent dicts with children embedded in their respective fields.
        """
        current_parent: dict | None = None
        children_by_field: dict[str, list] = {}

        # Build lookup: GID type -> field name
        type_to_field = {c["type"]: c["field"] for c in child_configs}

        for record in ShopifyBulkClient.stream_jsonl(jsonl_path):
            record_id = record.get("id", "")
            parent_id = record.get("__parentId")

            if parent_id is None and parent_type in record_id:
                # This is a parent record
                if current_parent is not None:
                    # Yield the previous parent with accumulated children
                    for field, items in children_by_field.items():
                        current_parent[field] = items
                    yield current_parent

                current_parent = record
                children_by_field = {c["field"]: [] for c in child_configs}

            elif parent_id is not None:
                # This is a child record — determine which type
                for child_type, field_name in type_to_field.items():
                    if child_type in record_id:
                        record.pop("__parentId", None)
                        children_by_field.setdefault(field_name, []).append(record)
                        break
            else:
                # Unknown record type, skip
                logger.debug(f"Skipping unrecognized record: {record_id}")

        # Yield the last parent
        if current_parent is not None:
            for field, items in children_by_field.items():
                current_parent[field] = items
            yield current_parent

    def execute_bulk_query(
        self,
        query: str,
        query_filter: str = "",
    ) -> Path:
        """
        Full lifecycle: submit → poll → download.

        Returns the path to the downloaded JSONL file.
        """
        op_id = self.run_bulk_query(query, query_filter)
        result = self.poll_until_complete(op_id)
        url = result.get("url")

        if not url:
            logger.info("Bulk operation returned no data (empty result set)")
            # Create an empty file
            tmp = tempfile.NamedTemporaryFile(
                suffix=".jsonl", prefix="shopify_bulk_empty_", delete=False
            )
            tmp.close()
            return Path(tmp.name)

        return self.download_jsonl(url)

    def _cancel_operation(self, operation_id: str) -> None:
        """Attempt to cancel a running bulk operation."""
        try:
            self.client.execute(
                BULK_OPERATION_CANCEL,
                variables={"id": operation_id},
            )
            logger.info(f"Cancelled bulk operation: {operation_id}")
        except Exception as e:
            logger.warning(f"Failed to cancel bulk operation: {e}")
