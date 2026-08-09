#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select

from pit_radar.db.models import AnalystSnapshot, DailyMarketBar, EstimateSnapshot, Security
from pit_radar.db.session import create_db_engine, create_session_factory
from pit_radar.time import ensure_utc


NY_TZ = ZoneInfo("America/New_York")
DEFAULT_UNIVERSE_FILE = Path("data/universe/core_symbols.txt")
DEFAULT_OUTPUT_DIR = Path("data/features")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a daily as-of feature table for backtests.")
    parser.add_argument("--trade-date", required=True, help="US trade date, YYYY-MM-DD.")
    parser.add_argument(
        "--cutoff",
        help="Feature cutoff timestamp. Defaults to the trade date market open, 09:30 America/New_York.",
    )
    parser.add_argument("--universe-file", default=str(DEFAULT_UNIVERSE_FILE))
    parser.add_argument("--output", help="Output CSV path. Defaults to data/features/daily_asof_features_<trade-date>.csv.")
    parser.add_argument("--include-missing-bars", action="store_true", help="Keep symbols without a price bar for trade date.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    trade_date = date.fromisoformat(args.trade_date)
    cutoff = parse_cutoff(args.cutoff, trade_date)
    output_path = Path(args.output) if args.output else DEFAULT_OUTPUT_DIR / f"daily_asof_features_{trade_date.isoformat()}.csv"
    symbols = read_symbol_file(Path(args.universe_file))
    if not symbols:
        raise SystemExit("No symbols found.")

    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    try:
        with session_factory() as session:
            securities = list(
                session.scalars(select(Security).where(Security.primary_ticker.in_(symbols))).all()
            )
            ordered_security_ids = [row.security_id for row in securities]

            bars = latest_bars(session, ordered_security_ids, trade_date, cutoff)
            estimates = latest_estimates(session, ordered_security_ids, trade_date, cutoff)
            analysts = latest_analysts(session, ordered_security_ids, cutoff)
            securities = dedupe_securities_by_symbol(securities, bars)

            rows = []
            for security in sorted(securities, key=lambda item: symbols.index(item.primary_ticker) if item.primary_ticker in symbols else 10**9):
                bar = bars.get(security.security_id)
                if bar is None and not args.include_missing_bars:
                    continue
                next_q = estimates.get((security.security_id, "quarter"))
                next_fy = estimates.get((security.security_id, "fiscal_year"))
                analyst = analysts.get(security.security_id)
                rows.append(feature_row(trade_date, cutoff, security, bar, next_q, next_fy, analyst))
    finally:
        engine.dispose()

    print(
        f"trade_date={trade_date} cutoff_utc={cutoff.isoformat()} symbols={len(symbols)} "
        f"securities={len(securities)} rows={len(rows)} output={output_path}",
        flush=True,
    )
    if args.dry_run:
        print(f"dry_run=true preview={','.join(row['symbol'] for row in rows[:20])}", flush=True)
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FEATURE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {output_path}", flush=True)


def latest_bars(
    session,
    security_ids: list[int],
    trade_date: date,
    cutoff: datetime,
) -> dict[int, DailyMarketBar]:
    rows = session.scalars(
        select(DailyMarketBar)
        .where(
            DailyMarketBar.security_id.in_(security_ids),
            DailyMarketBar.trade_date <= trade_date,
            DailyMarketBar.fetched_at <= cutoff,
        )
        .order_by(
            DailyMarketBar.security_id,
            DailyMarketBar.trade_date,
            DailyMarketBar.fetched_at,
            DailyMarketBar.recorded_at,
        )
    ).all()
    output: dict[int, DailyMarketBar] = {}
    for row in rows:
        output[row.security_id] = row
    return output


def dedupe_securities_by_symbol(
    securities: list[Security],
    bars: dict[int, DailyMarketBar],
) -> list[Security]:
    output: dict[str, Security] = {}
    for security in securities:
        existing = output.get(security.primary_ticker)
        if existing is None or _security_bar_key(security, bars) > _security_bar_key(existing, bars):
            output[security.primary_ticker] = security
    return list(output.values())


def _security_bar_key(security: Security, bars: dict[int, DailyMarketBar]) -> tuple:
    bar = bars.get(security.security_id)
    if bar is None:
        return (date.min, datetime.min.replace(tzinfo=UTC), security.security_id)
    return (bar.trade_date, ensure_utc(bar.fetched_at), security.security_id)


def latest_estimates(session, security_ids: list[int], trade_date: date, cutoff: datetime) -> dict[tuple[int, str], EstimateSnapshot]:
    rows = session.scalars(
        select(EstimateSnapshot)
        .where(
            EstimateSnapshot.security_id.in_(security_ids),
            EstimateSnapshot.fetched_at <= cutoff,
            EstimateSnapshot.fiscal_period_end >= trade_date,
        )
        .order_by(
            EstimateSnapshot.security_id,
            EstimateSnapshot.period_type,
            EstimateSnapshot.fiscal_period_end,
            EstimateSnapshot.fetched_at,
            EstimateSnapshot.recorded_at,
        )
    ).all()
    latest_by_period: dict[tuple[int, str, date], EstimateSnapshot] = {}
    for row in rows:
        latest_by_period[(row.security_id, row.period_type, row.fiscal_period_end)] = row

    output: dict[tuple[int, str], EstimateSnapshot] = {}
    for (security_id, period_type, period_end), row in sorted(latest_by_period.items(), key=lambda item: item[0][2]):
        output.setdefault((security_id, period_type), row)
    return output


def latest_analysts(session, security_ids: list[int], cutoff: datetime) -> dict[int, AnalystSnapshot]:
    rows = session.scalars(
        select(AnalystSnapshot)
        .where(AnalystSnapshot.security_id.in_(security_ids), AnalystSnapshot.fetched_at <= cutoff)
        .order_by(AnalystSnapshot.security_id, AnalystSnapshot.fetched_at, AnalystSnapshot.recorded_at)
    ).all()
    output: dict[int, AnalystSnapshot] = {}
    for row in rows:
        output[row.security_id] = row
    return output


def feature_row(
    trade_date: date,
    cutoff: datetime,
    security: Security,
    bar: DailyMarketBar | None,
    next_q: EstimateSnapshot | None,
    next_fy: EstimateSnapshot | None,
    analyst: AnalystSnapshot | None,
) -> dict[str, object]:
    return {
        "trade_date": trade_date.isoformat(),
        "cutoff_utc": cutoff.isoformat(),
        "security_id": security.security_id,
        "symbol": security.primary_ticker,
        "company_name": security.company_name,
        "sector": security.sector,
        "industry": security.industry,
        "country": security.country,
        "open": value(bar.open if bar else None),
        "high": value(bar.high if bar else None),
        "low": value(bar.low if bar else None),
        "close": value(bar.close if bar else None),
        "adjusted_close": value(bar.adjusted_close if bar else None),
        "volume": value(bar.volume if bar else None),
        "price_trade_date": iso_date(bar.trade_date if bar else None),
        "price_fetched_at": iso(bar.fetched_at if bar else None),
        "next_q_period_end": iso_date(next_q.fiscal_period_end if next_q else None),
        "next_q_eps_mean": value(next_q.eps_mean if next_q else None),
        "next_q_eps_high": value(next_q.eps_high if next_q else None),
        "next_q_eps_low": value(next_q.eps_low if next_q else None),
        "next_q_eps_analysts": next_q.analyst_count_eps if next_q else "",
        "next_q_revenue_mean": value(next_q.revenue_mean if next_q else None),
        "next_q_revenue_high": value(next_q.revenue_high if next_q else None),
        "next_q_revenue_low": value(next_q.revenue_low if next_q else None),
        "next_q_revenue_analysts": next_q.analyst_count_revenue if next_q else "",
        "next_q_estimate_fetched_at": iso(next_q.fetched_at if next_q else None),
        "next_fy_period_end": iso_date(next_fy.fiscal_period_end if next_fy else None),
        "next_fy_eps_mean": value(next_fy.eps_mean if next_fy else None),
        "next_fy_revenue_mean": value(next_fy.revenue_mean if next_fy else None),
        "next_fy_estimate_fetched_at": iso(next_fy.fetched_at if next_fy else None),
        "target_mean": value(analyst.target_mean if analyst else None),
        "target_high": value(analyst.target_high if analyst else None),
        "target_low": value(analyst.target_low if analyst else None),
        "strong_buy_count": analyst.strong_buy_count if analyst else "",
        "buy_count": analyst.buy_count if analyst else "",
        "hold_count": analyst.hold_count if analyst else "",
        "sell_count": analyst.sell_count if analyst else "",
        "strong_sell_count": analyst.strong_sell_count if analyst else "",
        "analyst_fetched_at": iso(analyst.fetched_at if analyst else None),
    }


FEATURE_COLUMNS = [
    "trade_date",
    "cutoff_utc",
    "security_id",
    "symbol",
    "company_name",
    "sector",
    "industry",
    "country",
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
    "volume",
    "price_trade_date",
    "price_fetched_at",
    "next_q_period_end",
    "next_q_eps_mean",
    "next_q_eps_high",
    "next_q_eps_low",
    "next_q_eps_analysts",
    "next_q_revenue_mean",
    "next_q_revenue_high",
    "next_q_revenue_low",
    "next_q_revenue_analysts",
    "next_q_estimate_fetched_at",
    "next_fy_period_end",
    "next_fy_eps_mean",
    "next_fy_revenue_mean",
    "next_fy_estimate_fetched_at",
    "target_mean",
    "target_high",
    "target_low",
    "strong_buy_count",
    "buy_count",
    "hold_count",
    "sell_count",
    "strong_sell_count",
    "analyst_fetched_at",
]


def parse_cutoff(value: str | None, trade_date: date) -> datetime:
    if value:
        return ensure_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    local = datetime.combine(trade_date, time(9, 30), tzinfo=NY_TZ)
    return local.astimezone(UTC)


def read_symbol_file(path: Path) -> list[str]:
    values: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        values.extend(stripped.replace(",", "\n").splitlines())
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        symbol = value.strip().upper().split()[0]
        if symbol and symbol not in seen:
            seen.add(symbol)
            output.append(symbol)
    return output


def value(item) -> str:
    if item is None:
        return ""
    if isinstance(item, Decimal):
        return format(item, "f")
    return str(item)


def iso(item: datetime | None) -> str:
    return ensure_utc(item).isoformat() if item else ""


def iso_date(item: date | None) -> str:
    return item.isoformat() if item else ""


if __name__ == "__main__":
    main()
