#!/usr/bin/env bash
set -uo pipefail

cd "$(dirname "$0")/.."
mkdir -p logs

LOG_FILE="${PIT_RADAR_LOG_FILE:-logs/macro_reminder_$(date +%Y%m%d_%H%M%S).log}"
STATUS_FILE="${PIT_RADAR_STATUS_FILE:-logs/macro_reminder.status}"
PID_FILE="${PIT_RADAR_PID_FILE:-logs/macro_reminder.pid}"
TASK_NAME="宏观提醒"
TASK_LABEL="com.aibao.pitradar.macro-reminder"

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

  export DATABASE_URL="${DATABASE_URL:-sqlite+pysqlite:///data/demo/pit_radar.sqlite}"
  export RAW_STORAGE_ROOT="${RAW_STORAGE_ROOT:-data/raw}"

  args=(
    --lookahead-days "${PIT_RADAR_MACRO_REMINDER_LOOKAHEAD_DAYS:-3}"
    --countries "${PIT_RADAR_MACRO_REMINDER_COUNTRIES:-US}"
    --impact-levels "${PIT_RADAR_MACRO_REMINDER_IMPACT_LEVELS:-High}"
  )
  if [ "${PIT_RADAR_MACRO_REMINDER_DRY_RUN:-0}" = "1" ]; then
    args+=(--dry-run)
  fi
  if [ "${PIT_RADAR_MACRO_REMINDER_IGNORE_STATE:-0}" = "1" ]; then
    args+=(--ignore-state)
  fi

  /Users/aibao/invest/.venv/bin/python -u scripts/macro_event_reminder.py "${args[@]}"
  exit_code=$?

  echo "finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ) exit_code=$exit_code" | tee -a "$STATUS_FILE"
  record_task_run "$exit_code"
  exit "$exit_code"
} 2>&1 | tee -a "$LOG_FILE"
