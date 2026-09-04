from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_local_settings(path: str | Path | None = None) -> None:
    config_path = Path(path) if path else Path(os.getenv("APP_CONFIG_PATH", PROJECT_ROOT / "config.txt"))
    if not config_path.exists():
        return

    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = [part.strip() for part in line.split("=", 1)]
        os.environ.setdefault(key, value)


load_dotenv(PROJECT_ROOT / ".env")
load_local_settings()


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_base_url: str = ""
    openai_model: str = "text-embedding-3-large"
    openai_api_version: str = "2024-02-01"
    openai_use_azure: bool = False
    jira_cosmos_endpoint: str = ""
    jira_cosmos_username: str = ""
    jira_cosmos_api_key: str = ""
    jira_cosmos_database: str = ""
    jira_cosmos_collections: tuple[str, ...] = field(default_factory=tuple)
    jira_vector_field: str = "Vector"
    cosmos_top_k: int = 5

    @classmethod
    def from_env(cls) -> "Settings":
        missing: list[str] = []

        openai_api_key = os.getenv("OPENAI_API_KEY") or os.getenv("AZURE_OPENAI_API_KEY")
        if not openai_api_key:
            missing.append("OPENAI_API_KEY")

        jira_cosmos_endpoint = os.getenv("JIRA_COSMOS_ENDPOINT")
        if not jira_cosmos_endpoint:
            missing.append("JIRA_COSMOS_ENDPOINT")

        jira_cosmos_username = os.getenv("JIRA_COSMOS_USERNAME")
        if not jira_cosmos_username:
            missing.append("JIRA_COSMOS_USERNAME")

        jira_cosmos_api_key = os.getenv("JIRA_COSMOS_API_KEY")
        if not jira_cosmos_api_key:
            missing.append("JIRA_COSMOS_API_KEY")

        jira_cosmos_database = os.getenv("JIRA_COSMOS_DATABASE")
        if not jira_cosmos_database:
            missing.append("JIRA_COSMOS_DATABASE")

        collections_raw = os.getenv("JIRA_COSMOS_COLLECTIONS")
        if collections_raw:
            collections = tuple(part.strip() for part in collections_raw.split(",") if part.strip())
        else:
            collections = (
                "jira_coll_ccrt",
                "jira_coll_csc",
                "jira_coll_b2bl3",
                "jira_coll_sre",
                "jira_coll_cpqgp",
                "jira_coll_cam",
                "jira_coll_tnt",
            )

        if missing:
            raise RuntimeError(
                "Missing required environment variables: " + ", ".join(missing)
            )

        openai_base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        openai_use_azure = (
            os.getenv("OPENAI_USE_AZURE", "").lower() in {"1", "true", "yes"}
            or "openai.azure.com" in openai_base_url.lower()
        )

        return cls(
            openai_api_key=openai_api_key,
            openai_base_url=openai_base_url,
            openai_model=os.getenv("OPENAI_MODEL", "text-embedding-3-large"),
            openai_api_version=os.getenv("OPENAI_API_VERSION", "2024-02-01"),
            openai_use_azure=openai_use_azure,
            jira_cosmos_endpoint=jira_cosmos_endpoint,
            jira_cosmos_username=jira_cosmos_username,
            jira_cosmos_api_key=jira_cosmos_api_key,
            jira_cosmos_database=jira_cosmos_database,
            jira_cosmos_collections=collections,
            jira_vector_field=os.getenv("JIRA_VECTOR_FIELD", "Vector"),
            cosmos_top_k=int(os.getenv("COSMOS_TOP_K", "5")),
        )
