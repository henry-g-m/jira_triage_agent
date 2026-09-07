from __future__ import annotations

import json
import argparse
import sys
import logging
from typing import Any

from app.cosmosdb_client.config import Settings
from app.cosmosdb_client.cosmos_client import get_container_client, retry_on_429

logging.basicConfig(level=logging.INFO)
_logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a ProjectKey query against Cosmos DB")
    parser.add_argument("--database", help="Database name (overrides config)")
    parser.add_argument("--collection", help="Collection/Container name (overrides config)")
    parser.add_argument("--project_key", required=True, help="ProjectKey to filter by (e.g. 'PROJ')")
    parser.add_argument("--top_k", type=int, help="Number of results", default=5)
    args = parser.parse_args()

    settings = Settings.from_env()
    database = args.database or settings.cosmos_database
    collection = args.collection or (settings. cosmos_container if settings.cosmos_container else None)
    if not database or not collection:
        print("Database or collection not configured.", file=sys.stderr)
        sys.exit(2)

    project_key = args.project_key
    top_k = args.top_k

    container = get_container_client(database, collection, settings=settings)

    query = (
        "SELECT TOP @topK c.id, c.Summary, c.Description, c.ProjectKey "
        "FROM c WHERE c.ProjectKey = @projectKey ORDER BY c._ts DESC"
    )

    params = [{"name": "@topK", "value": top_k}, {"name": "@projectKey", "value": project_key}]

    def run_query() -> list[Any]:
        return list(container.query_items(
            query=query,
            parameters=params,
            enable_cross_partition_query=True
        ))

    try:
        items = retry_on_429(run_query)
        print(json.dumps(items, indent=2, ensure_ascii=False))
    except Exception as exc:
        _logger.exception("Query failed")
        print(f"Query failed: {exc}", file=sys.stderr)
        sys.exit(3)


if __name__ == "__main__":
    main()
