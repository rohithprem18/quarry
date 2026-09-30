"""Settings, read from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # LLM access goes through Sluice (OpenAI-compatible); a direct Groq key works for local runs.
    llm_base_url: str = field(
        default_factory=lambda: os.getenv("QUARRY_LLM_BASE_URL", "https://sluice-orcin.vercel.app/v1")
    )
    llm_api_key: str = field(
        default_factory=lambda: os.getenv("QUARRY_LLM_API_KEY", os.getenv("SLUICE_KEY_QUARRY", ""))
    )
    llm_model: str = field(default_factory=lambda: os.getenv("QUARRY_LLM_MODEL", "sluice/smart"))

    data_dir: Path = field(default_factory=lambda: Path(os.getenv("QUARRY_DATA_DIR", ROOT / "data" / "dbs")))
    raw_dir: Path = field(default_factory=lambda: Path(os.getenv("QUARRY_RAW_DIR", ROOT / "data" / "raw")))

    redis_url: str = field(default_factory=lambda: os.getenv("UPSTASH_REDIS_REST_URL", ""))
    redis_token: str = field(default_factory=lambda: os.getenv("UPSTASH_REDIS_REST_TOKEN", ""))

    max_repairs: int = field(default_factory=lambda: _int("QUARRY_MAX_REPAIRS", 2))
    query_timeout_s: int = field(default_factory=lambda: _int("QUARRY_QUERY_TIMEOUT_S", 8))
    max_rows: int = field(default_factory=lambda: _int("QUARRY_MAX_ROWS", 500))
    asks_per_hour: int = field(default_factory=lambda: _int("QUARRY_ASKS_PER_HOUR", 20))
    asks_per_day_total: int = field(default_factory=lambda: _int("QUARRY_ASKS_PER_DAY", 300))


def get_settings() -> Settings:
    return Settings()
