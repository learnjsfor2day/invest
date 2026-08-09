#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p logs

LOG_FILE="${PIT_RADAR_LOG_FILE:-logs/valuation_radar_$(date +%Y%m%d_%H%M%S).log}"
STATUS_FILE="${PIT_RADAR_STATUS_FILE:-logs/valuation_radar.status}"

{
  echo "started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$STATUS_FILE"
  echo "log=$LOG_FILE" >> "$STATUS_FILE"
  echo "mode=observation_only_pit_20_60_session_labels" >> "$STATUS_FILE"

  export DATABASE_URL="${DATABASE_URL:-sqlite+pysqlite:///data/demo/pit_radar.sqlite}"
  /Users/aibao/invest/.venv/bin/python -u scripts/build_valuation_watchlists.py

  echo "finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ) exit_code=0" | tee -a "$STATUS_FILE"
} 2>&1 | tee -a "$LOG_FILE"
