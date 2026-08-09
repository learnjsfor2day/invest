from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field


class Settings(BaseModel):
    database_url: str = Field(
        default="postgresql+psycopg://pit_radar:pit_radar@localhost:5432/pit_radar"
    )
    raw_storage_root: Path = Field(default=Path("./data/raw"))
    fmp_base_url: str = Field(default="https://fmp-distribution.onrender.com/api/fmp")
    fmp_api_key: str = Field(default="")
    fmp_auth_mode: str = Field(default="query")
    fmp_rate_limit_per_minute: int = Field(default=540)
    fmp_max_retries: int = Field(default=2)
    default_symbols: list[str] = Field(default_factory=lambda: ["MU", "AAPL", "NVDA"])


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv()
    symbols = os.getenv("DEFAULT_SYMBOLS", "MU,AAPL,NVDA")
    return Settings(
        database_url=os.getenv("DATABASE_URL", Settings.model_fields["database_url"].default),
        raw_storage_root=Path(os.getenv("RAW_STORAGE_ROOT", "./data/raw")),
        fmp_base_url=os.getenv("FMP_BASE_URL", Settings.model_fields["fmp_base_url"].default),
        fmp_api_key=os.getenv("FMP_API_KEY", ""),
        fmp_auth_mode=os.getenv("FMP_AUTH_MODE", "query"),
        fmp_rate_limit_per_minute=int(os.getenv("FMP_RATE_LIMIT_PER_MINUTE", "540")),
        fmp_max_retries=int(os.getenv("FMP_MAX_RETRIES", "2")),
        default_symbols=[item.strip().upper() for item in symbols.split(",") if item.strip()],
    )
