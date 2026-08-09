#!/usr/bin/env bash
set -uo pipefail

cd "$(dirname "$0")/.."
mkdir -p logs

REPORT_FILE="${1:-logs/fmp_enrichment_check_$(date +%Y%m%d_%H%M%S).log}"
DB_URL="${DATABASE_URL:-sqlite+pysqlite:///data/demo/pit_radar.sqlite}"
RAW_ROOT="${RAW_STORAGE_ROOT:-data/raw}"

{
  echo "checked_at_local=$(date '+%Y-%m-%dT%H:%M:%S%z')"
  echo "checked_at_utc=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo "database_url=$DB_URL"
  echo

  echo "== launchctl =="
  launchctl list | grep 'com.aibao.pitradar.enrichment' || true
  echo

  echo "== status_file =="
  cat logs/fmp_enrichment.status 2>/dev/null || true
  echo

  echo "== latest_progress =="
  tail -n 100 logs/launchctl_fmp_enrichment_optimized.out 2>/dev/null || true
  echo

  echo "== dry_run_missing_summary =="
  DATABASE_URL="$DB_URL" \
  RAW_STORAGE_ROOT="$RAW_ROOT" \
  FMP_API_KEY=dummy \
  FMP_AUTH_MODE=query \
  /Users/aibao/invest/.venv/bin/python scripts/backfill_fmp_enrichment.py \
    --dry-run \
    --tasks estimates,earnings,financials,news,sec_filings \
    --chunk-size 40 \
    --max-workers 12
  echo

  echo "== database_counts =="
  DATABASE_URL="$DB_URL" \
  RAW_STORAGE_ROOT="$RAW_ROOT" \
  /Users/aibao/invest/.venv/bin/python - <<'PY'
from sqlalchemy import desc, distinct, func, select

from pit_radar.db.models import (
    AnalystSnapshot,
    EarningsCalendarSnapshot,
    EstimateSnapshot,
    FinancialFactSnapshot,
    IngestRun,
    NewsItemSnapshot,
    SecFilingSnapshot,
)
from pit_radar.db.session import create_session_factory

models = [
    ("estimate_snapshot", EstimateSnapshot),
    ("analyst_snapshot", AnalystSnapshot),
    ("earnings_calendar_snapshot", EarningsCalendarSnapshot),
    ("financial_fact_snapshot", FinancialFactSnapshot),
    ("news_item_snapshot", NewsItemSnapshot),
    ("sec_filing_snapshot", SecFilingSnapshot),
]

with create_session_factory()() as session:
    for name, model in models:
        rows = session.scalar(select(func.count()).select_from(model)) or 0
        symbols = session.scalar(select(func.count(distinct(model.security_id))).select_from(model)) or 0
        print(f"{name}: rows={rows} securities={symbols}")

    print("recent_ingest_runs:")
    for run in session.scalars(select(IngestRun).order_by(desc(IngestRun.run_id)).limit(12)):
        print(
            f"run_id={run.run_id} dataset={run.dataset_code} status={run.status} "
            f"requested={run.requested_count} success={run.success_count} "
            f"failed={run.failed_count} skipped={run.skipped_count}"
        )
PY
} 2>&1 | tee "$REPORT_FILE"

if command -v osascript >/dev/null 2>&1; then
  osascript -e "display notification \"FMP enrichment 检查完成，报告：$REPORT_FILE\" with title \"PIT Radar\""
fi
