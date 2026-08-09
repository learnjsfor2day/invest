#!/usr/bin/env bash
set -uo pipefail

cd "$(dirname "$0")/.."
mkdir -p logs

LOG_FILE="${PIT_RADAR_LOG_FILE:-logs/earnings_events_$(date +%Y%m%d_%H%M%S).log}"
STATUS_FILE="${PIT_RADAR_STATUS_FILE:-logs/earnings_events.status}"
PID_FILE="${PIT_RADAR_PID_FILE:-logs/earnings_events.pid}"
UNIVERSE_FILE="${PIT_RADAR_EARNINGS_UNIVERSE_FILE:-${PIT_RADAR_UNIVERSE_FILE:-data/universe/core_symbols.txt}}"
TASK_NAME="财报事件"
TASK_LABEL="com.aibao.pitradar.earnings"

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

  args=(
    --universe-file "$UNIVERSE_FILE"
    --from-offset-days "${PIT_RADAR_EARNINGS_FROM_OFFSET_DAYS:--1}"
    --to-offset-days "${PIT_RADAR_EARNINGS_TO_OFFSET_DAYS:-1}"
    --chunk-size "${PIT_RADAR_EARNINGS_CHUNK_SIZE:-40}"
    --max-workers "${PIT_RADAR_EARNINGS_MAX_WORKERS:-8}"
    --financial-limit "${PIT_RADAR_EARNINGS_FINANCIAL_LIMIT:-4}"
    --news-limit "${PIT_RADAR_EARNINGS_NEWS_LIMIT:-20}"
    --calendar-max-age-hours "${PIT_RADAR_EARNINGS_CALENDAR_MAX_AGE_HOURS:-18}"
    --min-event-rerun-hours "${PIT_RADAR_EARNINGS_MIN_RERUN_HOURS:-36}"
  )
  if [ "${PIT_RADAR_EARNINGS_IGNORE_EVENT_STATE:-0}" = "1" ]; then
    args+=(--ignore-event-state)
  fi
  if [ "${PIT_RADAR_EARNINGS_REFRESH_CALENDAR:-0}" = "0" ]; then
    args+=(--no-refresh-calendar)
  fi
  if [ "${PIT_RADAR_EARNINGS_DRY_RUN:-0}" = "1" ]; then
    args+=(--dry-run)
  fi

  /Users/aibao/invest/.venv/bin/python -u scripts/earnings_event_batch.py "${args[@]}"
  exit_code=$?

  echo "finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ) exit_code=$exit_code" | tee -a "$STATUS_FILE"
  record_task_run "$exit_code"
  exit "$exit_code"
} 2>&1 | tee -a "$LOG_FILE"
