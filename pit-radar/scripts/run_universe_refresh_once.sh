#!/usr/bin/env bash
set -uo pipefail

cd "$(dirname "$0")/.."
mkdir -p logs

LOG_FILE="${PIT_RADAR_LOG_FILE:-logs/universe_refresh_$(date +%Y%m%d_%H%M%S).log}"
STATUS_FILE="${PIT_RADAR_STATUS_FILE:-logs/universe_refresh.status}"
PID_FILE="${PIT_RADAR_PID_FILE:-logs/universe_refresh.pid}"
TASK_NAME="股票池刷新"
TASK_LABEL="com.aibao.pitradar.universe"
CORE_SIZE="${PIT_RADAR_CORE_UNIVERSE_SIZE:-1500}"
CORE_CSV="${PIT_RADAR_CORE_UNIVERSE_CSV:-data/universe/core_universe.csv}"
CORE_SYMBOLS="${PIT_RADAR_CORE_SYMBOLS_FILE:-data/universe/core_symbols.txt}"
CORE_MANIFEST="${PIT_RADAR_CORE_MANIFEST:-data/universe/core_manifest.json}"

record_task_run() {
  /Users/aibao/invest/.venv/bin/python -u scripts/record_task_run.py \
    --task "$TASK_NAME" \
    --label "$TASK_LABEL" \
    --status-file "$STATUS_FILE" \
    --log-file "$LOG_FILE" \
    --exit-code "$1" || true
}

{
  echo "$$" > "$PID_FILE"
  echo "started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$STATUS_FILE"
  echo "pid=$$" >> "$STATUS_FILE"
  echo "log=$LOG_FILE" >> "$STATUS_FILE"
  echo "core_size=$CORE_SIZE" >> "$STATUS_FILE"
  echo "core_symbols=$CORE_SYMBOLS" >> "$STATUS_FILE"

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

  /Users/aibao/invest/.venv/bin/python -u scripts/refresh_fmp_universe.py \
    --force \
    --limit "${PIT_RADAR_SCREENER_LIMIT:-1000}" \
    --screener-max-retries "${PIT_RADAR_SCREENER_MAX_RETRIES:-3}" \
    --screener-timeout-seconds "${PIT_RADAR_SCREENER_TIMEOUT_SECONDS:-30}"
  refresh_exit=$?
  echo "refresh_exit_code=$refresh_exit" >> "$STATUS_FILE"
  if [ "$refresh_exit" -ne 0 ]; then
    echo "finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ) exit_code=$refresh_exit" | tee -a "$STATUS_FILE"
    record_task_run "$refresh_exit"
    exit "$refresh_exit"
  fi

  /Users/aibao/invest/.venv/bin/python -u scripts/build_core_universe.py \
    --size "$CORE_SIZE" \
    --output-csv "$CORE_CSV" \
    --output-symbols "$CORE_SYMBOLS" \
    --manifest "$CORE_MANIFEST"
  core_exit=$?
  echo "core_exit_code=$core_exit" >> "$STATUS_FILE"
  if [ "$core_exit" -ne 0 ]; then
    echo "finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ) exit_code=$core_exit" | tee -a "$STATUS_FILE"
    record_task_run "$core_exit"
    exit "$core_exit"
  fi

  /Users/aibao/invest/.venv/bin/python -u scripts/backfill_universe_profile.py \
    --universe-csv "$CORE_CSV" \
    --manifest "$CORE_MANIFEST"
  backfill_exit=$?
  echo "backfill_exit_code=$backfill_exit" >> "$STATUS_FILE"

  echo "finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ) exit_code=$backfill_exit" | tee -a "$STATUS_FILE"
  record_task_run "$backfill_exit"
  exit "$backfill_exit"
} 2>&1 | tee -a "$LOG_FILE"
