from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import requests

if __package__ in {None, ""}:
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from app.config import Settings

OUTPUT_DIR = Path("../output")


def _is_vector_key(key: str, settings: Settings) -> bool:
    normalized = key.strip().lower().replace("-", "").replace("_", "")
    vector_field = settings.jira_vector_field.strip().lower().replace("-", "").replace("_", "")
    if normalized == vector_field:
        return True
    if normalized in {"vector", "embeddings", "embedding"}:
        return True
    return "vector" in normalized and "distance" not in normalized


def _clean_document(document: Any, settings: Settings) -> Any:
    if isinstance(document, dict):
        cleaned: dict[str, Any] = {}
        for key, value in document.items():
            if _is_vector_key(str(key), settings):
                continue
            processed = _clean_document(value, settings)
            if processed is None:
                continue
            cleaned[str(key)] = processed
        return cleaned

    if isinstance(document, list):
        cleaned_items = []
        for item in document:
            processed = _clean_document(item, settings)
            if processed is None:
                continue
            cleaned_items.append(processed)

        if not cleaned_items:
            return None

        if all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in cleaned_items):
            return None
        return cleaned_items

    if document is None:
        return None

    return document


def _fetch_collection_documents(collection_name: str, settings: Settings, limit: int = 1000) -> list[dict[str, Any]]:
    session = requests.Session()
    session.headers.update(
        {
            "X-Username": settings.jira_cosmos_username,
            "X-API-Key": settings.jira_cosmos_api_key,
            "Content-Type": "application/json",
        }
    )

    payload = {
        "databaseName": settings.jira_cosmos_database,
        "collectionName": collection_name,
        "query": {
            "queryText": "SELECT TOP @topK  c.id,c. NumericId,c.ProjectKey,c.Summary,c.Description,c.IssueType,c.Status,c.Resolution,c.Department,c.Comments,c.FullContextSummary FROM c ORDER BY c._ts DESC",
            "parameters": {"@topK": limit},
        },
    }

    response = session.post(settings.jira_cosmos_endpoint, json=payload, timeout=30)
    response.raise_for_status()
    body = response.json()

    if isinstance(body, list):
        return [item for item in body if isinstance(item, dict)]
    if isinstance(body, dict):
        value = body.get("value")
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        documents = body.get("documents")
        if isinstance(documents, list):
            return [item for item in documents if isinstance(item, dict)]
    return []


def _write_json_output(collection_name: str, documents: list[dict[str, Any]], settings: Settings) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cleaned_documents = [_clean_document(document, settings) for document in documents]
    cleaned_documents = [document for document in cleaned_documents if isinstance(document, dict)]

    output_path = OUTPUT_DIR / f"{collection_name}.json"
    print(f"Writing {len(cleaned_documents)} cleaned documents to {output_path.absolute()}")
    output_path.write_text(json.dumps(cleaned_documents, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def main() -> int:
    settings = Settings.from_env()
    collections = settings.jira_cosmos_collections
    if not collections:
        raise RuntimeError("No Cosmos collections were configured in JIRA_COSMOS_COLLECTIONS.")

    exported: list[str] = []
    for collection_name in collections:
        try:
            documents = _fetch_collection_documents(collection_name, settings, limit=10)
            output_path = _write_json_output(collection_name, documents, settings)
            exported.append(f"{collection_name}: {output_path} ({len(documents)} docs)")
        except Exception as exc:  # pragma: no cover - runtime guard for live Cosmos access
            print(f"Failed to export collection '{collection_name}': {exc}")

    if not exported:
        print("No collections were exported.")
        return 1

    print("Exported collections:")
    for line in exported:
        print(f"  - {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
