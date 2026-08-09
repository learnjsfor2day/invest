#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import time
from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from pit_radar.collectors import FmpDailyBarsCollector, FmpMacroCalendarCollector
from pit_radar.collectors.base import CollectionContext, DataCollector
from pit_radar.config import get_settings
from pit_radar.db.models import DailyMarketBar, Security
from pit_radar.db.session import create_db_engine, create_session_factory
from pit_radar.services.ingest import IngestService
from pit_radar.storage.local import LocalRawObjectStore
from pit_radar.time import utc_now
from sqlalchemy import select

NY_TZ = ZoneInfo("America/New_York")
DEFAULT_UNIVERSE_FILE = Path("data/universe/core_symbols.txt")
DEFAULT_UNIVERSE_MANIFEST = Path("data/universe/core_manifest.json")


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
    parser = argparse.ArgumentParser(description="Run a controlled FMP daily batch for PIT Radar.")
    parser.add_argument("--trade-date", help="US trading date to ingest, YYYY-MM-DD. Defaults to previous New York business day.")
    parser.add_argument("--symbols", help="Comma-separated tickers. Overrides --universe-file.")
    parser.add_argument("--universe-file", default=str(DEFAULT_UNIVERSE_FILE), help="Text/CSV file containing the daily stock universe.")
    parser.add_argument("--chunk-size", type=int, default=100, help="Symbols per ingest transaction.")
    parser.add_argument("--tasks", default="macro,prices", help="Comma-separated tasks: macro,prices.")
    parser.add_argument("--countries", default="US", help="Comma-separated macro countries, used by the macro task.")
    parser.add_argument("--mode", default="live", choices=["live", "backfill", "replay"], help="Collection mode.")
    parser.add_argument("--dry-run", action="store_true", help="Print the planned work without calling FMP.")
    parser.add_argument("--include-price-profile", action="store_true", help="Also fetch FMP profile during price collection.")
    parser.add_argument("--max-workers", type=int, default=8, help="Concurrent FMP price requests per chunk.")
    parser.add_argument("--retry-rounds", type=int, default=2, help="Retry rounds for symbols still missing the requested trade date.")
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True, help="Skip symbols that already have a daily bar for the trade date.")
    args = parser.parse_args()

    trade_date = date.fromisoformat(args.trade_date) if args.trade_date else previous_new_york_business_day()
    tasks = parse_tasks(args.tasks)
    symbols = load_symbols(args.symbols, Path(args.universe_file))
    if not symbols and "prices" in tasks:
        raise SystemExit("No symbols found. Pass --symbols or create data/universe/core_symbols.txt.")
    if not args.symbols and "prices" in tasks:
        warn_if_universe_stale(Path(args.universe_file), DEFAULT_UNIVERSE_MANIFEST)

    settings = get_settings()
    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    try:
        print(f"trade_date={trade_date}", flush=True)
        print(f"tasks={','.join(tasks)}", flush=True)
        print(f"fmp_rate_limit_per_minute={settings.fmp_rate_limit_per_minute}", flush=True)
        price_symbols = symbols
        if "prices" in tasks and args.resume:
            price_symbols = missing_price_symbols(symbols, trade_date, session_factory)
            print(f"resume=on skipped_existing={len(symbols) - len(price_symbols)} pending={len(price_symbols)}", flush=True)
        elif "prices" in tasks:
            print("resume=off", flush=True)
        if "prices" in tasks:
            price_requests = len(price_symbols) if not args.include_price_profile else len(price_symbols) * 2
            print(f"price_symbols={len(price_symbols)} chunk_size={args.chunk_size} max_workers={args.max_workers} estimated_price_requests={price_requests}", flush=True)
            print(f"price_profile={'on' if args.include_price_profile else 'off'}", flush=True)
        if args.dry_run:
            preview_symbols = price_symbols if "prices" in tasks else symbols
            preview = ",".join(preview_symbols[:20])
            print(f"dry_run=true preview_symbols={preview}{'...' if len(preview_symbols) > 20 else ''}", flush=True)
            return

        summaries: list[RunSummary] = []
        fetched_at = utc_now()
        if "macro" in tasks:
            countries = tuple(item.strip().upper() for item in args.countries.split(",") if item.strip())
            context = CollectionContext(
                collection_mode=args.mode,
                symbols=list(countries) or ["ALL"],
                fetched_at=fetched_at,
                from_date=trade_date,
                to_date=trade_date,
            )
            print("macro start", flush=True)
            summary = run_collector(FmpMacroCalendarCollector(countries=countries), context, session_factory)
            summaries.append(summary)
            print(
                f"macro done: status={summary.status} success={summary.success_count} "
                f"failed={summary.failed_count} skipped={summary.skipped_count}",
                flush=True,
            )

        if "prices" in tasks:
            summaries.extend(
                run_price_pass(
                    symbols=price_symbols,
                    trade_date=trade_date,
                    mode=args.mode,
                    fetched_at=fetched_at,
                    chunk_size=args.chunk_size,
                    include_profile=args.include_price_profile,
                    max_workers=args.max_workers,
                    label="main",
                    session_factory=session_factory,
                )
            )
            for retry_round in range(1, args.retry_rounds + 1):
                retry_symbols = missing_price_symbols(symbols, trade_date, session_factory)
                if not retry_symbols:
                    print(f"prices retry {retry_round}: no missing symbols", flush=True)
                    break
                print(f"prices retry {retry_round}: missing={len(retry_symbols)} preview={','.join(retry_symbols[:20])}", flush=True)
                summaries.extend(
                    run_price_pass(
                        symbols=retry_symbols,
                        trade_date=trade_date,
                        mode=args.mode,
                        fetched_at=fetched_at,
                        chunk_size=args.chunk_size,
                        include_profile=args.include_price_profile,
                        max_workers=args.max_workers,
                        label=f"retry{retry_round}",
                        session_factory=session_factory,
                    )
                )
            final_missing = missing_price_symbols(symbols, trade_date, session_factory)
            print(f"prices final_missing={len(final_missing)} preview={','.join(final_missing[:30])}", flush=True)
    finally:
        engine.dispose()

    print("summary", flush=True)
    for item in summaries:
        print(
            f"{item.job_name}: run_id={item.run_id} status={item.status} requested={item.requested_count} "
            f"success={item.success_count} failed={item.failed_count} skipped={item.skipped_count}",
            flush=True,
        )


def run_collector(collector: DataCollector, context: CollectionContext, session_factory) -> RunSummary:
    settings = get_settings()
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


def run_price_pass(
    symbols: list[str],
    trade_date: date,
    mode: str,
    fetched_at: datetime,
    chunk_size: int,
    include_profile: bool,
    max_workers: int,
    label: str,
    session_factory,
) -> list[RunSummary]:
    if not symbols:
        print(f"prices {label}: no symbols to run", flush=True)
        return []
    output: list[RunSummary] = []
    total_chunks = (len(symbols) + chunk_size - 1) // chunk_size
    price_started = time.monotonic()
    for chunk_index, chunk in enumerate(chunks(symbols, chunk_size), start=1):
        chunk_started = time.monotonic()
        print(f"prices {label} chunk {chunk_index}/{total_chunks} start: {chunk[0]}..{chunk[-1]} count={len(chunk)}", flush=True)
        context = CollectionContext(
            collection_mode=mode,
            symbols=chunk,
            fetched_at=fetched_at,
            from_date=trade_date,
            to_date=trade_date,
        )
        summary = run_collector(FmpDailyBarsCollector(include_profile=include_profile, max_workers=max_workers), context, session_factory)
        output.append(summary)
        elapsed = time.monotonic() - price_started
        average_chunk_seconds = elapsed / chunk_index
        remaining_seconds = average_chunk_seconds * (total_chunks - chunk_index)
        print(
            f"prices {label} chunk {chunk_index}/{total_chunks} done: status={summary.status} "
            f"success={summary.success_count} failed={summary.failed_count} skipped={summary.skipped_count} "
            f"chunk_elapsed={format_duration(time.monotonic() - chunk_started)} "
            f"total_elapsed={format_duration(elapsed)} eta={format_duration(remaining_seconds)}",
            flush=True,
        )
    return output


def missing_price_symbols(symbols: list[str], trade_date: date, session_factory) -> list[str]:
    if not symbols:
        return []
    with session_factory() as session:
        existing = set(
            session.scalars(
                select(Security.primary_ticker)
                .join(DailyMarketBar, DailyMarketBar.security_id == Security.security_id)
                .where(Security.primary_ticker.in_(symbols), DailyMarketBar.trade_date == trade_date)
            ).all()
        )
    return [symbol for symbol in symbols if symbol not in existing]


def load_symbols(symbols_arg: str | None, universe_file: Path) -> list[str]:
    if symbols_arg:
        return normalize_symbols(symbols_arg.replace("\n", ",").split(","))
    if universe_file.exists():
        return read_symbol_file(universe_file)
    settings = get_settings()
    return normalize_symbols(settings.default_symbols)


def warn_if_universe_stale(universe_file: Path, manifest_file: Path, max_age_days: int = 14) -> None:
    if not universe_file.exists():
        print(f"warning: {universe_file} not found; falling back to DEFAULT_SYMBOLS")
        return
    if not manifest_file.exists():
        print(f"warning: {manifest_file} not found; refresh the universe with scripts/refresh_fmp_universe.py every 14 days")
        return
    try:
        data = json.loads(manifest_file.read_text(encoding="utf-8"))
        generated_at = datetime.fromisoformat(str(data["generated_at"]).replace("Z", "+00:00"))
    except Exception:
        print(f"warning: could not parse {manifest_file}; refresh the universe")
        return
    age = utc_now() - generated_at
    if age > timedelta(days=max_age_days):
        print(f"warning: universe is {age.days} days old; refresh with scripts/refresh_fmp_universe.py")


def read_symbol_file(path: Path) -> list[str]:
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8", newline="") as file:
            sample = file.read(4096)
            file.seek(0)
            dialect = csv.Sniffer().sniff(sample) if sample.strip() else csv.excel
            reader = csv.DictReader(file, dialect=dialect)
            if reader.fieldnames:
                field_lookup = {field.lower(): field for field in reader.fieldnames}
                symbol_field = field_lookup.get("symbol") or field_lookup.get("ticker")
                if symbol_field:
                    return normalize_symbols(row.get(symbol_field, "") for row in reader)
            file.seek(0)
            return normalize_symbols(value for row in csv.reader(file, dialect=dialect) for value in row)
    values: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        values.extend(stripped.replace(",", "\n").splitlines())
    return normalize_symbols(values)


def normalize_symbols(values) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        symbol = str(value).strip().upper()
        if not symbol or symbol.startswith("#"):
            continue
        symbol = symbol.split()[0]
        if symbol and symbol not in seen:
            seen.add(symbol)
            output.append(symbol)
    return output


def previous_new_york_business_day(now: datetime | None = None) -> date:
    current = (now or utc_now()).astimezone(NY_TZ)
    candidate = current.date()
    if current.time() < datetime_time(16, 30):
        candidate -= timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def parse_tasks(value: str) -> list[str]:
    allowed = {"macro", "prices"}
    tasks = [item.strip().lower() for item in value.split(",") if item.strip()]
    invalid = sorted(set(tasks) - allowed)
    if invalid:
        raise SystemExit(f"Unsupported tasks: {','.join(invalid)}. Allowed: {','.join(sorted(allowed))}")
    return tasks or ["macro", "prices"]


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
