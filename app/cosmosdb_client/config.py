from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = MODULE_DIR / "config_azure.txt"


def load_local_settings(path: str | Path | None = None) -> None:
    """Load simple KEY=VALUE pairs from a local config file into the environment.

    Values are set only when the env var is not already present.
    """
    config_path = Path(path) if path else CONFIG_FILE
    if not config_path.exists():
        return

    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = [part.strip() for part in line.split("=", 1)]
        # strip quotes if present
        value = value.strip('"').strip("'")
        os.environ.setdefault(key, value)


# Load local config file on import so Settings.from_env() can rely on os.environ
load_local_settings()


@dataclass(frozen=True)
class Settings:
    cosmos_account_endpoint: str
    cosmos_account_key: str
    cosmos_database: str
    cosmos_container: str
    partition_key_path: str = "/ProjectKey"
    vector_field: str = "Vector"
    output_dir: str = "output"
    batch_size: int = 10
    llm_provider: str = "openai"

    @classmethod
    def from_env(cls) -> "Settings":
        endpoint = os.getenv("COSMOS_ACCOUNT_ENDPOINT", "").rstrip("/")
        key = os.getenv("COSMOS_ACCOUNT_KEY", "")
        database = os.getenv("COSMOS_DATABASE", "")
        container = os.getenv("COSMOS_CONTAINER", "")
        partition = os.getenv("PARTITION_KEY_PATH", "/ProjectKey")
        vector_field = os.getenv("VECTOR_FIELD", "Vector")
        output_dir = os.getenv("OUTPUT_DIR", "output")
        batch_size_raw = os.getenv("BATCH_SIZE", "10")
        llm_provider = os.getenv("LLM_PROVIDER", "openai")

        try:
            batch_size = int(batch_size_raw)
        except Exception:
            batch_size = 10

        missing = []
        if not endpoint:
            missing.append("COSMOS_ACCOUNT_ENDPOINT")
        if not key:
            missing.append("COSMOS_ACCOUNT_KEY")
        if not database:
            missing.append("COSMOS_DATABASE")
        if not container:
            missing.append("COSMOS_CONTAINER")

        if missing:
            raise RuntimeError("Missing required Azure Cosmos config: " + ", ".join(missing))

        return cls(
            cosmos_account_endpoint=endpoint,
            cosmos_account_key=key,
            cosmos_database=database,
            cosmos_container=container,
            partition_key_path=partition,
            vector_field=vector_field,
            output_dir=output_dir,
            batch_size=batch_size,
            llm_provider=llm_provider,
        )
