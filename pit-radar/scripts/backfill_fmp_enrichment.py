#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select
from pit_radar.collectors import (
    FmpEarningsCollector,
    FmpEstimatesCollector,
    FmpFinancialsCollector,
    FmpNewsCollector,
    FmpSecFilingsCollector,
)
from pit_radar.collectors.base import CollectionContext, DataCollector
from pit_radar.config import get_settings
from pit_radar.db.models import (
    AnalystSnapshot,
    DatasetCoverage,
    EarningsCalendarSnapshot,
    EstimateSnapshot,
    FinancialFactSnapshot,
    IngestRun,
    NewsItemSnapshot,
    SecFilingSnapshot,
    Security,
)
from pit_radar.db.session import create_db_engine, create_session_factory
from pit_radar.services.ingest import IngestService
from pit_radar.storage.local import LocalRawObjectStore
from pit_radar.time import ensure_utc, utc_now


DEFAULT_UNIVERSE_FILE = Path("data/universe/core_symbols.txt")
DEFAULT_STATUS_FILE = Path("logs/fmp_enrichment_status.json")
TASKS = {"estimates", "earnings", "financials", "news", "sec_filings"}
NO_DATA_RECHECK_DAYS = {
    "estimates": 7,
    "earnings": 7,
    "financials": 30,
    "news": 1,
    "sec_filings": 14,
}


@dataclass(frozen=True)
class RunSummary:
    task: str
    chunk_index: int
    chunk_count: int
    run_id: int
    status: str
    requested_count: int
    success_count: int
    failed_count: int
    skipped_count: int
    error_message: str | None = None


@dataclass(frozen=True)
class ResumePlan:
    pending: list[str]
    skipped_existing: int
    skipped_coverage: int
    skipped_completed: int = 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill FMP enrichment datasets for the daily universe.")
    parser.add_argument("--tasks", default="estimates,earnings,financials,news,sec_filings", help="Comma-separated tasks.")
    parser.add_argument("--symbols", help="Comma-separated tickers. Overrides --universe-file.")
    parser.add_argument("--universe-file", default=str(DEFAULT_UNIVERSE_FILE))
    parser.add_argument("--chunk-size", type=int, default=10)
    parser.add_argument("--max-workers", type=int, default=8, help="Concurrent symbols per chunk; still capped by FMP_RATE_LIMIT_PER_MINUTE.")
    parser.add_argument("--max-symbols", type=int, default=0, help="Cap symbols after resume filtering; 0 means all.")
    parser.add_argument("--include-profile", action="store_true", help="Also fetch FMP profile for each symbol/module.")
    parser.add_argument("--mode", default="live", choices=["live", "backfill", "replay"])
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--refresh-existing",
        action="store_true",
        help="Fetch symbols even when the target PIT table already has rows; still respects coverage cooldown.",
    )
    parser.add_argument("--ignore-coverage", action="store_true", help="Ignore no-data/transient coverage state and retry pending symbols.")
    parser.add_argument(
        "--skip-completed-coverage",
        action="store_true",
        help="Skip symbols marked ok in raw.dataset_coverage. Useful for resuming a failed refresh-existing snapshot.",
    )
    parser.add_argument("--status-file", default=str(DEFAULT_STATUS_FILE))
    parser.add_argument("--news-limit", type=int, default=10)
    parser.add_argument("--news-from-date")
    parser.add_argument("--news-to-date")
    parser.add_argument("--financial-periods", default="annual,quarter")
    parser.add_argument("--financial-limit", type=int, default=8)
    parser.add_argument("--sec-form-types", default="8-K,10-Q,10-K")
    parser.add_argument("--sec-limit", type=int, default=10)
    parser.add_argument("--sec-from-date")
    parser.add_argument("--sec-to-date")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    tasks = parse_tasks(args.tasks)
    symbols = load_symbols(args.symbols, Path(args.universe_file))
    if not symbols:
        raise SystemExit("No symbols found.")
    settings = get_settings()
    fetched_at = utc_now()
    print(f"tasks={','.join(tasks)}", flush=True)
    print(
        f"symbols={len(symbols)} chunk_size={args.chunk_size} "
        f"max_workers={args.max_workers} include_profile={args.include_profile}",
        flush=True,
    )
    print(f"fmp_rate_limit_per_minute={settings.fmp_rate_limit_per_minute}", flush=True)
    print(f"database_url={settings.database_url}", flush=True)

    status_file = Path(args.status_file)
    status_file.parent.mkdir(parents=True, exist_ok=True)
    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    try:
        ensure_coverage_table(session_factory)

        for task in tasks:
            resume_plan = (
                plan_symbols_for_task(
                    symbols,
                    task,
                    session_factory,
                    use_coverage=not args.ignore_coverage,
                    skip_existing=not args.refresh_existing,
                    skip_completed_coverage=args.skip_completed_coverage,
                )
                if args.resume
                else ResumePlan(list(symbols), 0, 0)
            )
            task_symbols = resume_plan.pending
            if args.max_symbols > 0:
                task_symbols = task_symbols[: args.max_symbols]
            print(
                f"{task} resume={'on' if args.resume else 'off'} "
                f"skipped_existing={resume_plan.skipped_existing} "
                f"skipped_coverage={resume_plan.skipped_coverage} "
                f"skipped_completed={resume_plan.skipped_completed} pending={len(task_symbols)}",
                flush=True,
            )
            print(f"{task} preview={','.join(task_symbols[:20])}", flush=True)
            write_status(status_file, task, task_symbols, started_at=fetched_at)
            if args.dry_run or not task_symbols:
                continue
            collector, from_date, to_date = build_collector(task, args)
            summaries = run_task(
                task=task,
                collector=collector,
                symbols=task_symbols,
                chunk_size=args.chunk_size,
                mode=args.mode,
                fetched_at=fetched_at,
                from_date=from_date,
                to_date=to_date,
                session_factory=session_factory,
            )
            final_plan = plan_symbols_for_task(
                symbols,
                task,
                session_factory,
                use_coverage=not args.ignore_coverage,
                skip_existing=not args.refresh_existing,
                skip_completed_coverage=args.skip_completed_coverage,
            )
            write_status(status_file, task, final_plan.pending, summaries=summaries, finished_at=utc_now())
    finally:
        engine.dispose()


def build_collector(task: str, args) -> tuple[DataCollector, date | None, date | None]:
    if task == "estimates":
        return FmpEstimatesCollector(max_workers=args.max_workers, include_profile=args.include_profile), None, None
    if task == "earnings":
        return FmpEarningsCollector(max_workers=args.max_workers, include_profile=args.include_profile), None, None
    if task == "financials":
        return (
            FmpFinancialsCollector(
                periods=parse_csv_tuple(args.financial_periods),
                limit=args.financial_limit,
                max_workers=args.max_workers,
                include_profile=args.include_profile,
            ),
            None,
            None,
        )
    if task == "news":
        return (
            FmpNewsCollector(limit=args.news_limit, max_workers=args.max_workers, include_profile=args.include_profile),
            date_or_none(args.news_from_date),
            date_or_none(args.news_to_date),
        )
    if task == "sec_filings":
        to_date = date_or_none(args.sec_to_date) or utc_now().date()
        from_date = date_or_none(args.sec_from_date) or (to_date - timedelta(days=365))
        return (
            FmpSecFilingsCollector(
                form_types=parse_csv_tuple(args.sec_form_types),
                limit=args.sec_limit,
                max_workers=args.max_workers,
                include_profile=args.include_profile,
            ),
            from_date,
            to_date,
        )
    raise SystemExit(f"Unsupported task: {task}")


def run_task(
    task: str,
    collector: DataCollector,
    symbols: list[str],
    chunk_size: int,
    mode: str,
    fetched_at: datetime,
    from_date: date | None,
    to_date: date | None,
    session_factory,
) -> list[RunSummary]:
    if chunk_size <= 0:
        raise SystemExit("--chunk-size must be positive")
    summaries: list[RunSummary] = []
    chunk_count = (len(symbols) + chunk_size - 1) // chunk_size
    started = time.monotonic()
    for chunk_index, chunk in enumerate(chunks(symbols, chunk_size), start=1):
        chunk_started = time.monotonic()
        print(f"{task} chunk {chunk_index}/{chunk_count} start: {chunk[0]}..{chunk[-1]} count={len(chunk)}", flush=True)
        context = CollectionContext(
            collection_mode=mode,
            symbols=chunk,
            fetched_at=fetched_at,
            from_date=from_date,
            to_date=to_date,
        )
        summary = run_collector(task, collector, context, chunk_index, chunk_count, session_factory)
        summaries.append(summary)
        update_coverage_after_chunk(task, chunk, summary, fetched_at, session_factory)
        elapsed = time.monotonic() - started
        average = elapsed / chunk_index
        eta = average * (chunk_count - chunk_index)
        print(
            f"{task} chunk {chunk_index}/{chunk_count} done: status={summary.status} "
            f"success={summary.success_count} failed={summary.failed_count} skipped={summary.skipped_count} "
            f"chunk_elapsed={format_duration(time.monotonic() - chunk_started)} "
            f"total_elapsed={format_duration(elapsed)} eta={format_duration(eta)}",
            flush=True,
        )
    return summaries


def run_collector(task: str, collector: DataCollector, context: CollectionContext, chunk_index: int, chunk_count: int, session_factory) -> RunSummary:
    settings = get_settings()
    with session_factory() as session:
        service = IngestService(session, LocalRawObjectStore(settings.raw_storage_root))
        run = service.ingest(collector, context)
        summary = RunSummary(
            task=task,
            chunk_index=chunk_index,
            chunk_count=chunk_count,
            run_id=run.run_id,
            status=run.status,
            requested_count=run.requested_count,
            success_count=run.success_count,
            failed_count=run.failed_count,
            skipped_count=run.skipped_count,
            error_message=run.error_message,
        )
        session.commit()
        return summary


def ensure_coverage_table(session_factory) -> None:
    with session_factory() as session:
        DatasetCoverage.__table__.create(bind=session.get_bind(), checkfirst=True)


def plan_symbols_for_task(
    symbols: list[str],
    task: str,
    session_factory=None,
    use_coverage: bool = True,
    skip_existing: bool = True,
    skip_completed_coverage: bool = False,
) -> ResumePlan:
    model = task_model(task)
    session_factory = session_factory or create_session_factory()
    now = utc_now()
    with session_factory() as session:
        existing = set()
        if skip_existing:
            existing = set(
                session.scalars(
                    select(Security.primary_ticker)
                    .join(model, model.security_id == Security.security_id)
                    .where(Security.primary_ticker.in_(symbols))
                    .group_by(Security.primary_ticker)
                    .having(func.count() > 0)
                ).all()
            )
        covered: set[str] = set()
        if use_coverage:
            rows = session.scalars(
                select(DatasetCoverage).where(
                    DatasetCoverage.source_code == "fmp",
                    DatasetCoverage.dataset_code == task,
                    DatasetCoverage.symbol.in_(symbols),
                )
            ).all()
            covered = {row.symbol for row in rows if _coverage_skips_now(row, now)}
            completed = {row.symbol for row in rows if skip_completed_coverage and row.status == "ok"}
        else:
            completed = set()
    pending = [symbol for symbol in symbols if symbol not in existing and symbol not in covered and symbol not in completed]
    return ResumePlan(
        pending=pending,
        skipped_existing=len(existing),
        skipped_coverage=len(covered - existing),
        skipped_completed=len(completed - existing - covered),
    )


def missing_symbols_for_task(symbols: list[str], task: str) -> list[str]:
    session_factory = create_session_factory()
    return plan_symbols_for_task(symbols, task, session_factory).pending


def update_coverage_after_chunk(task: str, symbols: list[str], summary: RunSummary, checked_at: datetime, session_factory) -> None:
    with session_factory() as session:
        data_symbols = symbols_with_task_data(session, symbols, task)
        securities = {
            row.primary_ticker: row
            for row in session.scalars(select(Security).where(Security.primary_ticker.in_(symbols))).all()
        }
        for symbol in symbols:
            symbol_error = _symbol_error(symbol, summary.error_message)
            if symbol in data_symbols:
                status = "ok"
                last_error = symbol_error
            else:
                status = classify_coverage_status(symbol_error)
                last_error = symbol_error or "no rows inserted"
            _upsert_coverage(session, task, symbol, status, checked_at, last_error, securities.get(symbol), summary)
        session.commit()


def symbols_with_task_data(session, symbols: list[str], task: str) -> set[str]:
    model = task_model(task)
    return set(
        session.scalars(
            select(Security.primary_ticker)
            .join(model, model.security_id == Security.security_id)
            .where(Security.primary_ticker.in_(symbols))
            .group_by(Security.primary_ticker)
            .having(func.count() > 0)
        ).all()
    )


def _upsert_coverage(
    session,
    task: str,
    symbol: str,
    status: str,
    checked_at: datetime,
    last_error: str | None,
    security: Security | None,
    summary: RunSummary,
) -> None:
    existing = session.scalar(
        select(DatasetCoverage).where(
            DatasetCoverage.source_code == "fmp",
            DatasetCoverage.dataset_code == task,
            DatasetCoverage.symbol == symbol,
        )
    )
    previous_failures = existing.failure_count if existing else 0
    failure_count = previous_failures + 1 if status == "transient_failed" else 0
    if existing is None:
        existing = DatasetCoverage(
            source_code="fmp",
            dataset_code=task,
            symbol=symbol,
            status=status,
            last_checked_at=ensure_utc(checked_at),
        )
        session.add(existing)
    existing.security_id = security.security_id if security else existing.security_id
    existing.status = status
    existing.last_checked_at = ensure_utc(checked_at)
    existing.next_check_after = next_check_after(task, status, ensure_utc(checked_at), failure_count)
    existing.failure_count = failure_count
    existing.last_error = _truncate_error(last_error)
    existing.metadata_json = {
        "run_id": summary.run_id,
        "chunk_index": summary.chunk_index,
        "chunk_count": summary.chunk_count,
        "run_status": summary.status,
    }


def _coverage_skips_now(row: DatasetCoverage, now: datetime) -> bool:
    if row.status not in {"no_data", "unsupported", "transient_failed"}:
        return False
    if row.next_check_after is None:
        return True
    return ensure_utc(row.next_check_after) > ensure_utc(now)


def classify_coverage_status(error_message: str | None) -> str:
    if not error_message:
        return "no_data"
    text = error_message.lower()
    no_data_markers = (
        "no analyst estimates returned",
        "no financial facts returned",
        "no matching news returned",
        "no matching filings returned",
        "not found",
        "empty",
        "no rows",
    )
    transient_markers = (
        "429",
        "timeout",
        "timed out",
        "connection",
        "remote disconnected",
        "incomplete read",
        "temporarily",
        "http 5",
        "failed after retries",
    )
    if any(marker in text for marker in no_data_markers):
        return "no_data"
    if any(marker in text for marker in transient_markers):
        return "transient_failed"
    if "invalid_api_key" in text or "unauthorized" in text or "401" in text:
        return "transient_failed"
    return "no_data"


def next_check_after(task: str, status: str, checked_at: datetime, failure_count: int = 0) -> datetime | None:
    if status == "ok":
        return None
    if status == "unsupported":
        return checked_at + timedelta(days=90)
    if status == "transient_failed":
        delay_days = 1 if failure_count <= 1 else min(7, 2 ** min(failure_count - 1, 3))
        return checked_at + timedelta(days=delay_days)
    return checked_at + timedelta(days=NO_DATA_RECHECK_DAYS.get(task, 7))


def _symbol_error(symbol: str, error_message: str | None) -> str | None:
    if not error_message:
        return None
    prefix = f"{symbol}:"
    lines = [line.strip() for line in error_message.splitlines() if line.strip().startswith(prefix)]
    return "\n".join(lines) or None


def _truncate_error(value: str | None, limit: int = 1000) -> str | None:
    if not value:
        return None
    return value if len(value) <= limit else value[: limit - 3] + "..."


def task_model(task: str):
    if task == "estimates":
        return EstimateSnapshot
    if task == "earnings":
        return EarningsCalendarSnapshot
    if task == "financials":
        return FinancialFactSnapshot
    if task == "news":
        return NewsItemSnapshot
    if task == "sec_filings":
        return SecFilingSnapshot
    raise SystemExit(f"Unsupported task: {task}")


def load_symbols(symbols_arg: str | None, universe_file: Path) -> list[str]:
    if symbols_arg:
        return normalize_symbols(symbols_arg.replace("\n", ",").split(","))
    if universe_file.suffix.lower() == ".csv":
        with universe_file.open("r", encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            return normalize_symbols(row.get("symbol", "") for row in reader)
    return normalize_symbols(line for line in universe_file.read_text(encoding="utf-8").splitlines() if not line.strip().startswith("#"))


def normalize_symbols(values) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        symbol = str(value).strip().upper().split()[0]
        if not symbol or symbol.startswith("#") or symbol in seen:
            continue
        seen.add(symbol)
        output.append(symbol)
    return output


def parse_tasks(value: str) -> list[str]:
    tasks = [item.strip().lower() for item in value.split(",") if item.strip()]
    invalid = sorted(set(tasks) - TASKS)
    if invalid:
        raise SystemExit(f"Unsupported tasks: {','.join(invalid)}. Allowed: {','.join(sorted(TASKS))}")
    return tasks or ["estimates", "earnings", "financials", "news", "sec_filings"]


def parse_csv_tuple(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def date_or_none(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def chunks(values: list[str], size: int):
    for index in range(0, len(values), size):
        yield values[index : index + size]


def write_status(
    path: Path,
    task: str,
    missing: list[str],
    started_at: datetime | None = None,
    summaries: list[RunSummary] | None = None,
    finished_at: datetime | None = None,
) -> None:
    payload = {
        "task": task,
        "updated_at": utc_now().isoformat(),
        "started_at": started_at.isoformat() if started_at else None,
        "finished_at": finished_at.isoformat() if finished_at else None,
        "missing_count": len(missing),
        "missing_preview": missing[:50],
        "runs": [summary.__dict__ for summary in summaries or []],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{seconds:02d}s"
    if minutes:
        return f"{minutes}m{seconds:02d}s"
    return f"{seconds}s"


if __name__ == "__main__":
    main()
