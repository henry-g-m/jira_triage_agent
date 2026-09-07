from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from dotenv import load_dotenv

# allow running the module directly from project tree
if __package__ in {None, ""}:
    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from app.config import Settings

# optional dependency; only import when needed
try:
    from azure.cosmos import CosmosClient, PartitionKey
except Exception:  # pragma: no cover - environment dependent
    CosmosClient = None

# OpenAI clients
try:
    from openai import AzureOpenAI, OpenAI
except Exception:  # pragma: no cover - environment dependent
    AzureOpenAI = None
    OpenAI = None


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_properties(path: Path) -> Dict[str, str]:
    props: Dict[str, str] = {}
    if not path.exists():
        return props
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = [p.strip() for p in line.split("=", 1)]
        props[k] = v
    return props


def _gather_json_files(output_dir: Path) -> List[Path]:
    print(f"Gathering JSON files from {output_dir.absolute()}")
    if not output_dir.exists():
        raise FileNotFoundError(f"output directory not found: {output_dir}")
    files = sorted(p for p in output_dir.glob("*.json") if p.is_file())
    return files


class JiraProjectsLoader:
    def __init__(self, config_path: Optional[Path] = None):
        load_dotenv(PROJECT_ROOT / ".env")
        self.props = _load_properties(config_path or (PROJECT_ROOT / "app" / "loader" / "config_loader.txt"))
        self.settings = Settings.from_env()

        # connection info precedence: props -> environment (via Settings or raw env)
        self.cosmos_endpoint = self.props.get("COSMOS_ACCOUNT_ENDPOINT") or self.settings.jira_cosmos_endpoint
        self.cosmos_key = self.props.get("COSMOS_ACCOUNT_KEY") or self.settings.jira_cosmos_api_key
        self.cosmos_database = self.props.get("COSMOS_DATABASE") or self.settings.jira_cosmos_database
        self.cosmos_container = self.props.get("COSMOS_CONTAINER") or None
        self.partition_key_path = self.props.get("PARTITION_KEY_PATH") or "/ProjectKey"
        self.vector_field = self.props.get("VECTOR_FIELD") or self.settings.jira_vector_field or "Vector"
        self.output_dir = Path(self.props.get("OUTPUT_DIR") or PROJECT_ROOT / "output")
        self.batch_size = int(self.props.get("BATCH_SIZE", "50"))

        # OpenAI client
        if self.settings.openai_use_azure and AzureOpenAI is not None:
            self.openai = AzureOpenAI(
                api_key=self.settings.openai_api_key,
                api_version=self.settings.openai_api_version,
                azure_endpoint=self.settings.openai_base_url,
            )
        elif OpenAI is not None:
            base_url = (self.settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")
            self.openai = OpenAI(api_key=self.settings.openai_api_key, base_url=base_url)
        else:
            self.openai = None

        # Cosmos client will be created lazily
        self._cosmos_client = None

    def _ensure_cosmos_client(self):
        if CosmosClient is None:
            raise RuntimeError("azure-cosmos is not installed in the environment")
        if not self.cosmos_endpoint or not self.cosmos_key:
            raise RuntimeError(
                "COSMOS_ACCOUNT_ENDPOINT and COSMOS_ACCOUNT_KEY must be set either in config_loader.txt or environment"
            )
        if self._cosmos_client is None:
            self._cosmos_client = CosmosClient(self.cosmos_endpoint, credential=self.cosmos_key)
        return self._cosmos_client

    def _get_or_create_container(self):
        client = self._ensure_cosmos_client()
        db = client.create_database_if_not_exists(self.cosmos_database)
        if not self.cosmos_container:
            # default to a container name derived from database
            self.cosmos_container = f"jira_vectors"
        try:
            container = db.create_container_if_not_exists(id=self.cosmos_container, partition_key=PartitionKey(path=self.partition_key_path), offer_throughput=400)
        except Exception:
            # fallback to attempting to get existing container
            container = db.get_container_client(self.cosmos_container)
        return container

    def _documents_from_file(self, json_path: Path) -> Iterable[Dict[str, Any]]:
        text = json_path.read_text(encoding="utf-8")
        items = json.loads(text)
        if isinstance(items, dict):
            # assume top-level object holds a list under some key
            # try common keys
            for key in ("value", "documents", "items", "docs"):
                if key in items and isinstance(items[key], list):
                    return items[key]
            # otherwise wrap
            return [items]
        if isinstance(items, list):
            return items
        return []

    def _doc_text_for_embedding(self, doc: Dict[str, Any]) -> str:
        parts: List[str] = []
        for key in ("Summary", "Description", "Comments", "issue_summary", "body"):
            val = doc.get(key)
            if not val:
                continue
            if isinstance(val, list):
                parts.append("\n".join(str(x) for x in val))
            else:
                parts.append(str(val))
        # fallback: collect short string fields
        if not parts:
            for k, v in doc.items():
                if isinstance(v, str) and len(v) < 2000:
                    parts.append(v)
        return "\n\n".join(parts)[:16000]

    def _embed_text(self, text: str) -> List[float]:
        if not self.openai:
            raise RuntimeError("OpenAI client not configured (OPENAI_API_KEY or LLM settings missing)")
        # model name from settings
        model = self.settings.openai_model
        resp = self.openai.embeddings.create(model=model, input=text)
        return resp.data[0].embedding

    def load(self) -> None:
        files = _gather_json_files(self.output_dir)
        if not files:
            print(f"No JSON files found in {self.output_dir}")
            return

        container = self._get_or_create_container()
        total = 0
        for file_path in files:
            docs = list(self._documents_from_file(file_path))
            print(f"Processing {file_path.name}: {len(docs)} documents")
            for doc in docs:
                # attach embedding
                try:
                    text = self._doc_text_for_embedding(doc)
                    if not text:
                        print("  skipping doc (no textual content)")
                        continue
                    embedding = self._embed_text(text)
                    doc[self.vector_field] = embedding

                    # ensure partition key exists if required
                    pk = self.partition_key_path.lstrip("/")
                    if pk and pk not in doc:
                        # try to set a conservative partition value
                        doc[pk] = doc.get("ProjectKey") or doc.get("project") or str(doc.get("id") or doc.get("IssueKey") or "unknown")

                    container.upsert_item(doc)
                    total += 1
                except Exception as exc:  # pragma: no cover - runtime guards
                    print(f"  failed to process item: {exc}")
        print(f"Finished. Upserted {total} documents into {self.cosmos_database}/{self.cosmos_container}")


def main() -> int:
    loader = JiraProjectsLoader()
    try:
        loader.load()
    except Exception as e:  # pragma: no cover - CLI runtime
        print(f"Loader failed: {e}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
