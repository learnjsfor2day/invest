#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from pathlib import Path
import time
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from pit_radar.collectors import FmpDailyBarsCollector
from pit_radar.collectors.base import CollectionContext
from pit_radar.config import get_settings
from pit_radar.db.models import DailyMarketBar, RawPayload, Security
from pit_radar.db.session import create_db_engine, create_session_factory
from pit_radar.services.ingest import IngestService
from pit_radar.storage.local import LocalRawObjectStore
from pit_radar.time import utc_now


NY_TZ = ZoneInfo("America/New_York")
DEFAULT_UNIVERSE_FILE = Path("data/universe/core_symbols.txt")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill multi-year split-adjusted FMP daily bars for the core universe."
    )
    parser.add_argument("--from-date", default="2023-01-01")
    parser.add_argument("--to-date", default=None)
    parser.add_argument("--universe-file", default=str(DEFAULT_UNIVERSE_FILE))
    parser.add_argument("--symbols", help="Comma-separated tickers; overrides universe file")
    parser.add_argument("--chunk-size", type=int, default=25)
    parser.add_argument("--max-workers", type=int, default=8)
    parser.add_argument("--retry-rounds", type=int, default=2)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    from_date = date.fromisoformat(args.from_date)
    to_date = date.fromisoformat(args.to_date) if args.to_date else previous_new_york_business_day()
    if from_date >= to_date:
        raise SystemExit("--from-date must be earlier than --to-date")
    symbols = load_symbols(args.symbols, Path(args.universe_file))
    if not symbols:
        raise SystemExit("No symbols found")

    settings = get_settings()
    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    try:
        pending = symbols if args.force else missing_history_symbols(
            symbols, from_date, to_date, session_factory
        )
        print(
            f"range={from_date}..{to_date} universe={len(symbols)} "
            f"covered={len(symbols) - len(pending)} pending={len(pending)}",
            flush=True,
        )
        print(
            f"estimated_requests={len(pending)} chunk_size={args.chunk_size} "
            f"max_workers={args.max_workers} rate_limit={settings.fmp_rate_limit_per_minute}/min",
            flush=True,
        )
        if args.dry_run:
            print(f"preview={','.join(pending[:30])}", flush=True)
            return

        for round_index in range(args.retry_rounds + 1):
            if not pending:
                break
            label = "initial" if round_index == 0 else f"retry-{round_index}"
            run_pass(
                pending,
                from_date,
                to_date,
                args.chunk_size,
                args.max_workers,
                label,
                session_factory,
                settings.raw_storage_root,
            )
            pending = missing_history_symbols(symbols, from_date, to_date, session_factory)
            print(f"{label} remaining={len(pending)}", flush=True)
        if pending:
            print(f"incomplete_symbols={','.join(pending[:100])}", flush=True)
            raise SystemExit(1)
    finally:
        engine.dispose()


def run_pass(
    symbols: list[str],
    from_date: date,
    to_date: date,
    chunk_size: int,
    max_workers: int,
    label: str,
    session_factory,
    raw_storage_root: Path,
) -> None:
    chunks = [symbols[index : index + chunk_size] for index in range(0, len(symbols), chunk_size)]
    started = time.monotonic()
    for chunk_index, chunk in enumerate(chunks, start=1):
        context = CollectionContext(
            collection_mode="backfill",
            symbols=chunk,
            fetched_at=utc_now(),
            from_date=from_date,
            to_date=to_date,
        )
        with session_factory() as session:
            service = IngestService(session, LocalRawObjectStore(raw_storage_root))
            run = service.ingest(
                FmpDailyBarsCollector(include_profile=False, max_workers=max_workers),
                context,
            )
            session.commit()
        elapsed = time.monotonic() - started
        average = elapsed / chunk_index
        eta = average * (len(chunks) - chunk_index)
        print(
            f"{label} chunk={chunk_index}/{len(chunks)} symbols={chunk[0]}..{chunk[-1]} "
            f"status={run.status} success={run.success_count} failed={run.failed_count} "
            f"elapsed={elapsed:.0f}s eta={eta:.0f}s",
            flush=True,
        )


def missing_history_symbols(
    symbols: list[str],
    from_date: date,
    to_date: date,
    session_factory,
) -> list[str]:
    tolerance = from_date + timedelta(days=7)
    request_suffix = f":{from_date}:{to_date}"
    with session_factory() as session:
        rows = session.execute(
            select(Security.primary_ticker, func.min(DailyMarketBar.trade_date))
            .join(DailyMarketBar, DailyMarketBar.security_id == Security.security_id)
            .where(Security.primary_ticker.in_(symbols))
            .group_by(Security.primary_ticker)
        ).all()
        payload_keys = session.scalars(
            select(RawPayload.request_key).where(
                RawPayload.dataset_code == "daily_bars",
                RawPayload.request_key.like(
                    f"fmp-daily-bars:%:{from_date}:{to_date}"
                ),
            )
        ).all()
    covered = {symbol for symbol, earliest in rows if earliest and earliest <= tolerance}
    # A successful response is complete even when the company listed after the
    # requested start date and therefore cannot have bars back to from_date.
    for request_key in payload_keys:
        if request_key.startswith("fmp-daily-bars:") and request_key.endswith(request_suffix):
            covered.add(request_key[len("fmp-daily-bars:") : -len(request_suffix)])
    return [symbol for symbol in symbols if symbol not in covered]


def load_symbols(symbols_arg: str | None, universe_file: Path) -> list[str]:
    if symbols_arg:
        values = symbols_arg.replace("\n", ",").split(",")
    elif universe_file.exists():
        values = universe_file.read_text(encoding="utf-8").splitlines()
    else:
        values = get_settings().default_symbols
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        symbol = str(value).strip().upper().split()[0] if str(value).strip() else ""
        if symbol and not symbol.startswith("#") and symbol not in seen:
            seen.add(symbol)
            output.append(symbol)
    return output


def previous_new_york_business_day() -> date:
    candidate = datetime.now(NY_TZ).date() - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


if __name__ == "__main__":
    main()
