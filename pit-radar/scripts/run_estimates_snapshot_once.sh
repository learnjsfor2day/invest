#!/usr/bin/env bash
set -uo pipefail

cd "$(dirname "$0")/.."
mkdir -p logs

LOG_FILE="${PIT_RADAR_LOG_FILE:-logs/estimates_snapshot_$(date +%Y%m%d_%H%M%S).log}"
STATUS_FILE="${PIT_RADAR_STATUS_FILE:-logs/estimates_snapshot.status}"
PID_FILE="${PIT_RADAR_PID_FILE:-logs/estimates_snapshot.pid}"
CHUNK_SIZE="${PIT_RADAR_ESTIMATES_CHUNK_SIZE:-40}"
MAX_WORKERS="${PIT_RADAR_ESTIMATES_MAX_WORKERS:-8}"
UNIVERSE_FILE="${PIT_RADAR_ESTIMATES_UNIVERSE_FILE:-${PIT_RADAR_UNIVERSE_FILE:-data/universe/core_symbols.txt}}"
SKIP_COMPLETED_COVERAGE="${PIT_RADAR_ESTIMATES_SKIP_COMPLETED_COVERAGE:-0}"

record_task_run() {
  local exit_code="$1"
  /Users/aibao/invest/.venv/bin/python scripts/record_task_run.py \
    --task "分析师预测" \
    --label "com.aibao.pitradar.estimates" \
    --status-file "$STATUS_FILE" \
    --log-file "$LOG_FILE" \
    --exit-code "$exit_code" || true
}

{
  echo "$$" > "$PID_FILE"
  echo "started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$STATUS_FILE"
  echo "pid=$$" >> "$STATUS_FILE"
  echo "log=$LOG_FILE" >> "$STATUS_FILE"
  echo "tasks=estimates" >> "$STATUS_FILE"
  echo "chunk_size=$CHUNK_SIZE" >> "$STATUS_FILE"
  echo "max_workers=$MAX_WORKERS" >> "$STATUS_FILE"
  echo "universe_file=$UNIVERSE_FILE" >> "$STATUS_FILE"
  echo "snapshot_mode=daily_refresh_hash_dedupe" >> "$STATUS_FILE"
  echo "skip_completed_coverage=$SKIP_COMPLETED_COVERAGE" >> "$STATUS_FILE"

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
    --tasks estimates
    --universe-file "$UNIVERSE_FILE"
    --refresh-existing
    --chunk-size "$CHUNK_SIZE"
    --max-workers "$MAX_WORKERS"
  )
  if [ "$SKIP_COMPLETED_COVERAGE" = "1" ]; then
    args+=(--skip-completed-coverage)
  fi

  /Users/aibao/invest/.venv/bin/python -u scripts/backfill_fmp_enrichment.py \
    "${args[@]}"
  exit_code=$?

  echo "finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ) exit_code=$exit_code" | tee -a "$STATUS_FILE"
  record_task_run "$exit_code"
  exit "$exit_code"
} 2>&1 | tee -a "$LOG_FILE"
