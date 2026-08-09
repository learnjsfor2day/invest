#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select

from pit_radar.collectors import FmpEarningsCollector, FmpFinancialsCollector, FmpNewsCollector, FmpSecFilingsCollector
from pit_radar.collectors.base import CollectionContext, DataCollector
from pit_radar.config import get_settings
from pit_radar.db.models import EarningsCalendarSnapshot, FinancialFactSnapshot, NewsItemSnapshot, SecFilingSnapshot, Security
from pit_radar.db.session import create_session_factory
from pit_radar.services.ingest import IngestService
from pit_radar.storage.local import LocalRawObjectStore
from pit_radar.time import utc_now


NY_TZ = ZoneInfo("America/New_York")
DEFAULT_UNIVERSE_FILE = Path("data/universe/core_symbols.txt")
DEFAULT_CALENDAR_STATUS_FILE = Path("logs/earnings_calendar_refresh.status")
DEFAULT_EVENT_STATE_FILE = Path("logs/earnings_event_symbol_state.json")


@dataclass(frozen=True)
class RunSummary:
    job_name: str
    run_id: int
    status: str
    requested_count: int
    success_count: int
    failed_count: int
    skipped_count: int


def main() -> None:
    parser = argparse.ArgumentParser(description="Run event-driven earnings snapshots for symbols near their report date.")
    parser.add_argument("--symbols", help="Comma-separated tickers. Overrides --universe-file.")
    parser.add_argument("--universe-file", default=str(DEFAULT_UNIVERSE_FILE))
    parser.add_argument("--from-date", help="Earnings report window start, YYYY-MM-DD.")
    parser.add_argument("--to-date", help="Earnings report window end, YYYY-MM-DD.")
    parser.add_argument("--from-offset-days", type=int, default=-1, help="Default start offset from current New York date.")
    parser.add_argument("--to-offset-days", type=int, default=1, help="Default end offset from current New York date.")
    parser.add_argument(
        "--refresh-calendar",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Explicitly refresh the full earnings calendar before selecting event symbols. Default is off for scheduled event runs.",
    )
    parser.add_argument("--calendar-max-age-hours", type=int, default=18)
    parser.add_argument("--calendar-status-file", default=str(DEFAULT_CALENDAR_STATUS_FILE))
    parser.add_argument("--chunk-size", type=int, default=40)
    parser.add_argument("--max-workers", type=int, default=8)
    parser.add_argument("--financial-periods", default="annual,quarter")
    parser.add_argument("--financial-limit", type=int, default=4)
    parser.add_argument("--news-limit", type=int, default=20)
    parser.add_argument("--filings-lookback-days", type=int, default=3)
    parser.add_argument("--filings-lookahead-days", type=int, default=1)
    parser.add_argument("--mode", default="live", choices=["live", "backfill", "replay"])
    parser.add_argument("--event-state-file", default=str(DEFAULT_EVENT_STATE_FILE))
    parser.add_argument("--min-event-rerun-hours", type=int, default=36, help="Skip symbols already attempted within this many hours.")
    parser.add_argument("--ignore-event-state", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    symbols = load_symbols(args.symbols, Path(args.universe_file))
    if not symbols:
        raise SystemExit("No symbols found.")

    now = utc_now()
    ny_today = now.astimezone(NY_TZ).date()
    from_date = date.fromisoformat(args.from_date) if args.from_date else ny_today + timedelta(days=args.from_offset_days)
    to_date = date.fromisoformat(args.to_date) if args.to_date else ny_today + timedelta(days=args.to_offset_days)
    if to_date < from_date:
        raise SystemExit("--to-date must be >= --from-date")

    settings = get_settings()
    print(f"window={from_date}..{to_date}", flush=True)
    print(f"symbols={len(symbols)}", flush=True)
    print(f"database_url={settings.database_url}", flush=True)
    print(f"fmp_rate_limit_per_minute={settings.fmp_rate_limit_per_minute}", flush=True)

    if args.refresh_calendar and calendar_refresh_due(Path(args.calendar_status_file), args.calendar_max_age_hours):
        print("earnings calendar refresh start", flush=True)
        if not args.dry_run:
            refresh_earnings_calendar(
                symbols=symbols,
                fetched_at=now,
                mode=args.mode,
                chunk_size=args.chunk_size,
                max_workers=args.max_workers,
                status_file=Path(args.calendar_status_file),
            )
        else:
            print("dry_run=true skip calendar refresh", flush=True)
    elif args.refresh_calendar:
        print("earnings calendar refresh skipped: status file is fresh", flush=True)
    else:
        print("earnings calendar refresh disabled", flush=True)

    targets = earnings_event_symbols(symbols, from_date, to_date)
    skipped_recent: list[str] = []
    if not args.ignore_event_state:
        targets, skipped_recent = filter_recent_event_symbols(
            targets,
            Path(args.event_state_file),
            args.min_event_rerun_hours,
            now,
        )
    print(
        f"event_symbols={len(targets)} skipped_recent={len(skipped_recent)} "
        f"preview={','.join(targets[:30])}",
        flush=True,
    )
    if args.dry_run or not targets:
        return

    summaries = run_event_snapshots(
        symbols=targets,
        fetched_at=now,
        mode=args.mode,
        chunk_size=args.chunk_size,
        max_workers=args.max_workers,
        financial_periods=parse_csv_tuple(args.financial_periods),
        financial_limit=args.financial_limit,
        news_limit=args.news_limit,
        filings_from=from_date - timedelta(days=args.filings_lookback_days),
        filings_to=to_date + timedelta(days=args.filings_lookahead_days),
    )
    update_event_symbol_state(Path(args.event_state_file), targets, now, from_date, to_date)
    print("summary", flush=True)
    for item in summaries:
        print(
            f"{item.job_name}: run_id={item.run_id} status={item.status} requested={item.requested_count} "
            f"success={item.success_count} failed={item.failed_count} skipped={item.skipped_count}",
            flush=True,
        )


def refresh_earnings_calendar(
    symbols: list[str],
    fetched_at: datetime,
    mode: str,
    chunk_size: int,
    max_workers: int,
    status_file: Path,
) -> None:
    summaries: list[RunSummary] = []
    total_chunks = (len(symbols) + chunk_size - 1) // chunk_size
    started = time.monotonic()
    for chunk_index, chunk in enumerate(chunks(symbols, chunk_size), start=1):
        print(f"earnings calendar chunk {chunk_index}/{total_chunks} start: {chunk[0]}..{chunk[-1]} count={len(chunk)}", flush=True)
        context = CollectionContext(collection_mode=mode, symbols=chunk, fetched_at=fetched_at)
        summary = run_collector(FmpEarningsCollector(max_workers=max_workers, include_profile=False), context)
        summaries.append(summary)
        elapsed = time.monotonic() - started
        print(
            f"earnings calendar chunk {chunk_index}/{total_chunks} done: status={summary.status} "
            f"success={summary.success_count} failed={summary.failed_count} skipped={summary.skipped_count} "
            f"elapsed={format_duration(elapsed)}",
            flush=True,
        )
    status_file.parent.mkdir(parents=True, exist_ok=True)
    status_file.write_text(
        json.dumps(
            {
                "finished_at": utc_now().isoformat(),
                "symbols": len(symbols),
                "runs": [summary.__dict__ for summary in summaries],
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )


def run_event_snapshots(
    symbols: list[str],
    fetched_at: datetime,
    mode: str,
    chunk_size: int,
    max_workers: int,
    financial_periods: tuple[str, ...],
    financial_limit: int,
    news_limit: int,
    filings_from: date,
    filings_to: date,
) -> list[RunSummary]:
    output: list[RunSummary] = []
    total_chunks = (len(symbols) + chunk_size - 1) // chunk_size
    for chunk_index, chunk in enumerate(chunks(symbols, chunk_size), start=1):
        print(f"earnings event chunk {chunk_index}/{total_chunks} start: {chunk[0]}..{chunk[-1]} count={len(chunk)}", flush=True)
        context = CollectionContext(
            collection_mode=mode,
            symbols=chunk,
            fetched_at=fetched_at,
            from_date=filings_from,
            to_date=filings_to,
        )
        collectors: list[DataCollector] = [
            FmpEarningsCollector(max_workers=max_workers, include_profile=False),
            FmpFinancialsCollector(periods=financial_periods, limit=financial_limit, max_workers=max_workers, include_profile=False),
            FmpNewsCollector(limit=news_limit, max_workers=max_workers, include_profile=False),
            FmpSecFilingsCollector(form_types=("8-K", "10-Q", "10-K"), limit=50, max_workers=max_workers, include_profile=False),
        ]
        for collector in collectors:
            output.append(run_collector(collector, context))
        print(f"earnings event chunk {chunk_index}/{total_chunks} done", flush=True)
    return output


def run_collector(collector: DataCollector, context: CollectionContext) -> RunSummary:
    settings = get_settings()
    session_factory = create_session_factory()
    with session_factory() as session:
        service = IngestService(session, LocalRawObjectStore(settings.raw_storage_root))
        run = service.ingest(collector, context)
        summary = RunSummary(
            job_name=run.job_name,
            run_id=run.run_id,
            status=run.status,
            requested_count=run.requested_count,
            success_count=run.success_count,
            failed_count=run.failed_count,
            skipped_count=run.skipped_count,
        )
        session.commit()
        return summary


def earnings_event_symbols(universe_symbols: list[str], from_date: date, to_date: date) -> list[str]:
    universe = set(universe_symbols)
    session_factory = create_session_factory()
    with session_factory() as session:
        rows = session.scalars(
            select(Security.primary_ticker)
            .join(EarningsCalendarSnapshot, EarningsCalendarSnapshot.security_id == Security.security_id)
            .where(
                Security.primary_ticker.in_(universe_symbols),
                EarningsCalendarSnapshot.expected_report_date >= from_date,
                EarningsCalendarSnapshot.expected_report_date <= to_date,
            )
            .distinct()
            .order_by(Security.primary_ticker)
        ).all()
    return [symbol for symbol in rows if symbol in universe]


def calendar_refresh_due(path: Path, max_age_hours: int) -> bool:
    if max_age_hours <= 0 or not path.exists():
        return True
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        finished_at = datetime.fromisoformat(str(data["finished_at"]).replace("Z", "+00:00"))
    except Exception:
        return True
    return utc_now() - finished_at >= timedelta(hours=max_age_hours)


def filter_recent_event_symbols(
    symbols: list[str],
    state_file: Path,
    min_rerun_hours: int,
    now: datetime,
) -> tuple[list[str], list[str]]:
    if min_rerun_hours <= 0:
        return symbols, []
    cutoff = now - timedelta(hours=min_rerun_hours)
    state = read_event_state(state_file) if state_file.exists() else {}
    already_enriched = recent_event_enriched_symbols(symbols, cutoff)
    output: list[str] = []
    skipped: list[str] = []
    for symbol in symbols:
        if symbol in already_enriched:
            skipped.append(symbol)
            continue
        last_run_text = state.get(symbol, {}).get("last_run_at")
        if not last_run_text:
            output.append(symbol)
            continue
        try:
            last_run = datetime.fromisoformat(str(last_run_text).replace("Z", "+00:00"))
        except ValueError:
            output.append(symbol)
            continue
        if last_run >= cutoff:
            skipped.append(symbol)
        else:
            output.append(symbol)
    return output, skipped


def recent_event_enriched_symbols(symbols: list[str], cutoff: datetime) -> set[str]:
    if not symbols:
        return set()
    recent: set[str] = set()
    session_factory = create_session_factory()
    models = (FinancialFactSnapshot, SecFilingSnapshot, NewsItemSnapshot)
    with session_factory() as session:
        for model in models:
            rows = session.scalars(
                select(Security.primary_ticker)
                .join(model, model.security_id == Security.security_id)
                .where(Security.primary_ticker.in_(symbols), model.fetched_at >= cutoff)
                .distinct()
            ).all()
            recent.update(rows)
    return recent


def update_event_symbol_state(
    state_file: Path,
    symbols: list[str],
    now: datetime,
    from_date: date,
    to_date: date,
) -> None:
    state = read_event_state(state_file)
    for symbol in symbols:
        state[symbol] = {
            "last_run_at": now.isoformat(),
            "window_from": str(from_date),
            "window_to": str(to_date),
        }
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_event_state(path: Path) -> dict[str, dict[str, str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    output: dict[str, dict[str, str]] = {}
    for symbol, payload in data.items():
        if isinstance(payload, dict):
            output[str(symbol).upper()] = {str(key): str(value) for key, value in payload.items()}
    return output


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


def parse_csv_tuple(value: str) -> tuple[str, ...]:
    return tuple(item.strip().lower() for item in value.split(",") if item.strip())


def chunks(values: list[str], size: int):
    if size <= 0:
        raise SystemExit("--chunk-size must be positive")
    for index in range(0, len(values), size):
        yield values[index : index + size]


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
