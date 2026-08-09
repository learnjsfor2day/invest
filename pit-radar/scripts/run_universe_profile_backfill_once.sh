#!/usr/bin/env bash
set -uo pipefail

cd "$(dirname "$0")/.."
mkdir -p logs

LOG_FILE="${PIT_RADAR_LOG_FILE:-logs/universe_profile_backfill_$(date +%Y%m%d_%H%M%S).log}"
STATUS_FILE="${PIT_RADAR_STATUS_FILE:-logs/universe_profile_backfill.status}"
PID_FILE="${PIT_RADAR_PID_FILE:-logs/universe_profile_backfill.pid}"

{
  echo "$$" > "$PID_FILE"
  echo "started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$STATUS_FILE"
  echo "pid=$$" >> "$STATUS_FILE"
  echo "log=$LOG_FILE" >> "$STATUS_FILE"

  export DATABASE_URL="${DATABASE_URL:-sqlite+pysqlite:///data/demo/pit_radar.sqlite}"
  export RAW_STORAGE_ROOT="${RAW_STORAGE_ROOT:-data/raw}"

  /Users/aibao/invest/.venv/bin/python -u scripts/backfill_universe_profile.py "$@"
  exit_code=$?

  echo "finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ) exit_code=$exit_code" | tee -a "$STATUS_FILE"
  exit "$exit_code"
} 2>&1 | tee -a "$LOG_FILE"
