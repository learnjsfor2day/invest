#!/usr/bin/env bash
set -uo pipefail

cd "$(dirname "$0")/.."
mkdir -p logs

LOG_FILE="${PIT_RADAR_LOG_FILE:-logs/fmp_enrichment_$(date +%Y%m%d_%H%M%S).log}"
STATUS_FILE="${PIT_RADAR_STATUS_FILE:-logs/fmp_enrichment.status}"
PID_FILE="${PIT_RADAR_PID_FILE:-logs/fmp_enrichment.pid}"

{
  echo "$$" > "$PID_FILE"
  echo "started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$STATUS_FILE"
  echo "pid=$$" >> "$STATUS_FILE"
  echo "log=$LOG_FILE" >> "$STATUS_FILE"

  if [ -z "${FMP_API_KEY:-}" ]; then
    FMP_API_KEY="$(
      /Users/aibao/invest/.venv/bin/python - <<'PY'
import re
from pathlib import Path

text = Path("../fmp_api_smoke_test.py").read_text(encoding="utf-8")
match = re.search(r"fmpd_[^\s\"']+", text)
if not match:
    raise SystemExit("FMP key not found")
print(match.group(0))
PY
    )"
    export FMP_API_KEY
  fi

  export DATABASE_URL="${DATABASE_URL:-sqlite+pysqlite:///data/demo/pit_radar.sqlite}"
  export RAW_STORAGE_ROOT="${RAW_STORAGE_ROOT:-data/raw}"
  export FMP_AUTH_MODE="${FMP_AUTH_MODE:-query}"
  export FMP_RATE_LIMIT_PER_MINUTE="${FMP_RATE_LIMIT_PER_MINUTE:-540}"
  export FMP_MAX_RETRIES="${FMP_MAX_RETRIES:-2}"

  /Users/aibao/invest/.venv/bin/python -u scripts/backfill_fmp_enrichment.py "$@"
  exit_code=$?

  echo "finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ) exit_code=$exit_code" | tee -a "$STATUS_FILE"
  exit "$exit_code"
} 2>&1 | tee -a "$LOG_FILE"
