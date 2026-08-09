#!/usr/bin/env bash
set -uo pipefail

cd "$(dirname "$0")/.."
mkdir -p logs

if [ -n "${PIT_RADAR_TRADE_DATE:-}" ]; then
  TRADE_DATE="$PIT_RADAR_TRADE_DATE"
else
  TRADE_DATE="$(
    /Users/aibao/invest/.venv/bin/python - <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, str(Path("scripts").resolve()))
from daily_fmp_batch import previous_new_york_business_day

print(previous_new_york_business_day())
PY
  )"
fi
TASKS="${PIT_RADAR_TASKS:-prices}"
CHUNK_SIZE="${PIT_RADAR_CHUNK_SIZE:-50}"
MAX_WORKERS="${PIT_RADAR_MAX_WORKERS:-8}"
RETRY_ROUNDS="${PIT_RADAR_RETRY_ROUNDS:-2}"
UNIVERSE_FILE="${PIT_RADAR_UNIVERSE_FILE:-data/universe/core_symbols.txt}"
LOG_FILE="${PIT_RADAR_LOG_FILE:-logs/daily_fmp_${TRADE_DATE}_$(date +%Y%m%d_%H%M%S).log}"
STATUS_FILE="${PIT_RADAR_STATUS_FILE:-logs/daily_fmp_${TRADE_DATE}.status}"
PID_FILE="${PIT_RADAR_PID_FILE:-logs/daily_fmp_${TRADE_DATE}.pid}"
TASK_NAME="日线快照"
TASK_LABEL="com.aibao.pitradar.daily"

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
  echo "trade_date=$TRADE_DATE" >> "$STATUS_FILE"
  echo "tasks=$TASKS" >> "$STATUS_FILE"
  echo "chunk_size=$CHUNK_SIZE" >> "$STATUS_FILE"
  echo "max_workers=$MAX_WORKERS" >> "$STATUS_FILE"
  echo "retry_rounds=$RETRY_ROUNDS" >> "$STATUS_FILE"
  echo "universe_file=$UNIVERSE_FILE" >> "$STATUS_FILE"

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

  /Users/aibao/invest/.venv/bin/python -u scripts/daily_fmp_batch.py \
    --trade-date "$TRADE_DATE" \
    --tasks "$TASKS" \
    --universe-file "$UNIVERSE_FILE" \
    --chunk-size "$CHUNK_SIZE" \
    --max-workers "$MAX_WORKERS" \
    --retry-rounds "$RETRY_ROUNDS"
  exit_code=$?

  echo "finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ) exit_code=$exit_code" | tee -a "$STATUS_FILE"
  record_task_run "$exit_code"
  exit "$exit_code"
} 2>&1 | tee -a "$LOG_FILE"
