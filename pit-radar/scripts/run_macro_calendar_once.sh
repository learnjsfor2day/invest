#!/usr/bin/env bash
set -uo pipefail

cd "$(dirname "$0")/.."
mkdir -p logs

LOG_FILE="${PIT_RADAR_LOG_FILE:-logs/macro_calendar_$(date +%Y%m%d_%H%M%S).log}"
STATUS_FILE="${PIT_RADAR_STATUS_FILE:-logs/macro_calendar.status}"
PID_FILE="${PIT_RADAR_PID_FILE:-logs/macro_calendar.pid}"
COUNTRIES="${PIT_RADAR_MACRO_COUNTRIES:-US}"
TASK_NAME="宏观日历"
TASK_LABEL="com.aibao.pitradar.macro"

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
  echo "countries=$COUNTRIES" >> "$STATUS_FILE"

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

  args=(ingest fmp-macro-calendar --mode "${PIT_RADAR_MACRO_MODE:-live}" --countries "$COUNTRIES")
  if [ -n "${PIT_RADAR_MACRO_FROM_DATE:-}" ]; then
    args+=(--from-date "$PIT_RADAR_MACRO_FROM_DATE")
  fi
  if [ -n "${PIT_RADAR_MACRO_TO_DATE:-}" ]; then
    args+=(--to-date "$PIT_RADAR_MACRO_TO_DATE")
  fi

  RUN_OUTPUT="$(mktemp)"
  /Users/aibao/invest/.venv/bin/pit-radar "${args[@]}" | tee "$RUN_OUTPUT"
  command_exit=${PIPESTATUS[0]}
  if grep -Eq "fmp:macro_events:.*status=(failed|partial_success)|fmp:macro_events:.*failed=[1-9]" "$RUN_OUTPUT"; then
    exit_code=1
  else
    exit_code=$command_exit
  fi
  echo "command_exit_code=$command_exit" >> "$STATUS_FILE"
  rm -f "$RUN_OUTPUT"

  echo "finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ) exit_code=$exit_code" | tee -a "$STATUS_FILE"
  record_task_run "$exit_code"
  exit "$exit_code"
} 2>&1 | tee -a "$LOG_FILE"
