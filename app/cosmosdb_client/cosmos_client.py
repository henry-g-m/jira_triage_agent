from __future__ import annotations

import os
import threading
import time
import logging
from typing import Optional

from azure.cosmos import CosmosClient  # type: ignore
from azure.cosmos.exceptions import CosmosHttpResponseError  # type: ignore

from app.config import Settings

_logger = logging.getLogger(__name__)

_client_lock = threading.Lock()
_client: Optional[CosmosClient] = None


def _get_env_endpoint_and_key(settings: Optional[Settings]) -> tuple[str, str]:
    """Resolve the endpoint and key from environment or settings.

    Priority: explicit COSMOS_ACCOUNT_* env vars -> settings.jira_cosmos_* values.
    """
    endpoint = os.getenv("COSMOS_ACCOUNT_ENDPOINT") or (settings.jira_cosmos_endpoint if settings else "")
    key = os.getenv("COSMOS_ACCOUNT_KEY") or (settings.jira_cosmos_api_key if settings else "")

    if not endpoint or not key:
        raise RuntimeError(
            "Cosmos DB endpoint and key are required. Set COSMOS_ACCOUNT_ENDPOINT/COSMOS_ACCOUNT_KEY or the JIRA_COSMOS_* env vars."
        )

    return endpoint.rstrip("/"), key


def get_client(settings: Optional[Settings] = None) -> CosmosClient:
    """Return a process-wide singleton CosmosClient instance.

    Call with a Settings instance if you already have one (avoids re-reading env).
    This follows the "sdk-singleton-client" best-practice: reuse the client for the
    lifetime of the application.
    """
    global _client
    if _client:
        return _client

    with _client_lock:
        if _client:
            return _client

        settings = settings or Settings.from_env()
        endpoint, key = _get_env_endpoint_and_key(settings)

        # Create the client. Keep configuration minimal to avoid depending on
        # non-standard SDK types here; callers can configure additional options
        # (preferred regions, connection mode) by constructing their own client
        # if needed.
        client = CosmosClient(endpoint, key, user_agent_suffix="CosmosDB_RAG/1.0")
        _client = client
        _logger.info("Initialized CosmosClient for %s", endpoint)
        return _client


def _sleep_for_retry(exc: CosmosHttpResponseError) -> None:
    """Determine a backoff from response headers when possible, otherwise use exponential backoff."""
    try:
        # Some SDKs expose retry-after-ms via headers; try common header names.
        headers = getattr(exc, "headers", {}) or {}
        retry_ms = None
        for hdr in ("x-ms-retry-after-ms", "retry-after-ms", "retry-after"):
            if hdr in headers:
                try:
                    retry_ms = int(headers[hdr])
                except Exception:
                    try:
                        # some servers provide seconds in Retry-After
                        retry_ms = int(float(headers[hdr]) * 1000)
                    except Exception:
                        retry_ms = None
                break

        if retry_ms:
            time.sleep(max(0.1, retry_ms / 1000.0))
            return
    except Exception:
        pass

    # Fallback: short sleep
    time.sleep(1.0)


def get_database_client(database_name: str, create_if_not_exists: bool = False, settings: Optional[Settings] = None):
    """Return a DatabaseClient for database_name. Optionally create it if missing.

    Example:
        db = get_database_client("mydb")
    """
    client = get_client(settings)
    try:
        if create_if_not_exists:
            return client.create_database_if_not_exists(database_name)
        return client.get_database_client(database_name)
    except CosmosHttpResponseError as exc:
        # Surface helpful error message
        _logger.exception("Failed to get database client for %s", database_name)
        raise


def get_container_client(database_name: str, container_name: str, partition_key: Optional[str] = None, create_if_not_exists: bool = False, settings: Optional[Settings] = None):
    """Return a ContainerClient for the specified container. Optionally create it.

    If create_if_not_exists is True, partition_key must be provided.
    """
    if create_if_not_exists and not partition_key:
        raise ValueError("partition_key is required when create_if_not_exists=True")

    db = get_database_client(database_name, create_if_not_exists=create_if_not_exists, settings=settings)

    try:
        if create_if_not_exists:
            return db.create_container_if_not_exists(id=container_name, partition_key=partition_key)
        return db.get_container_client(container_name)
    except CosmosHttpResponseError as exc:
        _logger.exception("Failed to get container client %s/%s", database_name, container_name)
        raise


def retry_on_429(func, *args, max_retries: int = 5, initial_backoff: float = 0.5, **kwargs):
    """Run func with retry handling for 429 (throttling) responses.

    The function should be a callable that interacts with the SDK (e.g., a single SDK call).
    This helper retries using exponential backoff and honors server-provided retry headers
    when available.
    """
    backoff = initial_backoff
    for attempt in range(1, max_retries + 1):
        try:
            return func(*args, **kwargs)
        except CosmosHttpResponseError as exc:
            # 429 is a throttled response
            status = getattr(exc, "status_code", None)
            if status == 429 or (hasattr(exc, "message") and "Request rate" in str(exc)):
                _logger.warning("Cosmos DB throttled (attempt %s/%s), backing off %s seconds", attempt, max_retries, backoff)
                # Prefer header-guided sleep when available
                try:
                    _sleep_for_retry(exc)
                except Exception:
                    time.sleep(backoff)
                backoff = min(backoff * 2, 30)
                continue
            raise
    raise RuntimeError("Exceeded retries due to repeated 429 throttling")
