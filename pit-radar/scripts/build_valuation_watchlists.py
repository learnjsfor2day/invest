#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path

import pandas as pd

from pit_radar.db.session import create_db_engine
from pit_radar.valuation_radar import (
    ValuationRadarConfig,
    build_valuation_radar,
    evaluate_matured_history,
    load_visible_bars,
    select_watchlists,
    write_valuation_outputs,
)


def _parse_as_of(value: str | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    parsed = pd.Timestamp(value)
    if parsed.tzinfo is None:
        parsed = parsed.tz_localize("UTC")
    return parsed.tz_convert("UTC").to_pydatetime()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build strict PIT value-trough and overvaluation observation watchlists. "
            "This does not emit buy/sell orders."
        )
    )
    parser.add_argument("--as-of", help="UTC cutoff; defaults to the current time")
    parser.add_argument("--output-dir", default="data/valuation_radar")
    parser.add_argument("--watchlist-size", type=int, default=30)
    parser.add_argument("--minimum-price", type=float, default=3.0)
    parser.add_argument("--minimum-market-cap", type=float, default=300_000_000.0)
    parser.add_argument("--minimum-dollar-volume", type=float, default=5_000_000.0)
    parser.add_argument("--minimum-data-coverage", type=float, default=0.45)
    args = parser.parse_args()

    as_of = _parse_as_of(args.as_of)
    config = ValuationRadarConfig(
        watchlist_size=args.watchlist_size,
        minimum_price=args.minimum_price,
        minimum_market_cap=args.minimum_market_cap,
        minimum_dollar_volume=args.minimum_dollar_volume,
        minimum_data_coverage=args.minimum_data_coverage,
    )
    output_dir = Path(args.output_dir)
    engine = create_db_engine()
    try:
        radar, audit = build_valuation_radar(engine, as_of, config)
        bars = load_visible_bars(engine, as_of)
    finally:
        engine.dispose()

    value, overvalued = select_watchlists(radar, config)
    evaluation = evaluate_matured_history(output_dir / "history", bars, config)
    paths = write_valuation_outputs(
        output_dir,
        radar,
        value,
        overvalued,
        audit,
        evaluation,
        config,
    )

    print(
        f"signal_date={audit['signal_date']} eligible={audit['eligible_symbols']} "
        f"value_watch={len(value)} overvaluation_watch={len(overvalued)}",
        flush=True,
    )
    print(f"audit={json.dumps(audit, ensure_ascii=False)}", flush=True)
    print("value_trough_watchlist", flush=True)
    for row in value.itertuples():
        print(
            f"{row.watch_rank:>2} {row.symbol:<8} value={row.value_trough_score:5.1f} "
            f"cheap={row.cheapness_score:5.1f} quality={row.quality_score:5.1f} "
            f"expect={row.expectation_support_score:5.1f} {row.value_reason}",
            flush=True,
        )
    print("overvaluation_watchlist", flush=True)
    for row in overvalued.itertuples():
        print(
            f"{row.watch_rank:>2} {row.symbol:<8} overvaluation={row.overvaluation_score:5.1f} "
            f"expensive={row.expensiveness_score:5.1f} quality={row.quality_score:5.1f} "
            f"expect={row.expectation_support_score:5.1f} {row.overvaluation_reason}",
            flush=True,
        )
    for name, path in paths.items():
        print(f"{name}_output={path}", flush=True)


if __name__ == "__main__":
    main()
