"""Config: env vars, paths."""
from __future__ import annotations
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "invest.db"

# Optional: load .env if present (no python-dotenv dep — minimal parser)
_env_file = ROOT / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

FMP_API_KEY = os.environ.get("FMP_API_KEY", "").strip()
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
LARK_WEBHOOK_URL = os.environ.get("LARK_WEBHOOK_URL", "").strip()

# SEC EDGAR requires a User-Agent identifying you (free, no key)
SEC_USER_AGENT = os.environ.get(
    "SEC_USER_AGENT",
    "invest-monitor research@example.com",
)

LLM_MODEL = os.environ.get("LLM_MODEL", "claude-haiku-4-5-20251001")


def has_fmp() -> bool:
    return bool(FMP_API_KEY)


def has_anthropic() -> bool:
    return bool(ANTHROPIC_API_KEY)


def has_lark() -> bool:
    return bool(LARK_WEBHOOK_URL)
