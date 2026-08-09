#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path

import pandas as pd

from pit_radar.db.session import create_db_engine
from pit_radar.inflection_radar import (
    InflectionRadarConfig,
    build_inflection_radar,
    evaluate_forward_labels,
    select_inflection_watchlist,
    write_inflection_outputs,
)
from pit_radar.valuation_radar import load_visible_bars


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
            "Build a point-in-time medium-horizon fundamental inflection watchlist "
            "and evaluate matured 20/60/120-session labels."
        )
    )
    parser.add_argument("--as-of", help="UTC cutoff; defaults to now")
    parser.add_argument("--output-dir", default="data/inflection_radar")
    parser.add_argument("--watchlist-size", type=int, default=20)
    parser.add_argument("--minimum-price", type=float, default=3.0)
    parser.add_argument("--minimum-market-cap", type=float, default=300_000_000.0)
    parser.add_argument("--minimum-dollar-volume", type=float, default=5_000_000.0)
    parser.add_argument("--minimum-data-coverage", type=float, default=0.30)
    args = parser.parse_args()

    as_of = _parse_as_of(args.as_of)
    config = InflectionRadarConfig(
        watchlist_size=args.watchlist_size,
        minimum_price=args.minimum_price,
        minimum_market_cap=args.minimum_market_cap,
        minimum_dollar_volume=args.minimum_dollar_volume,
        minimum_data_coverage=args.minimum_data_coverage,
    )
    output_dir = Path(args.output_dir)
    engine = create_db_engine()
    try:
        radar, audit = build_inflection_radar(engine, as_of, config)
        bars = load_visible_bars(engine, as_of)
    finally:
        engine.dispose()

    watchlist = select_inflection_watchlist(radar, config)
    labels, evaluation = evaluate_forward_labels(output_dir / "history", bars, config)
    paths = write_inflection_outputs(
        output_dir,
        radar,
        watchlist,
        labels,
        audit,
        evaluation,
        config,
    )

    print(
        f"signal_date={audit['signal_date']} eligible={audit['eligible_symbols']} "
        f"watchlist={len(watchlist)} median_coverage={audit['median_data_coverage']:.1%}",
        flush=True,
    )
    print(f"forward_evaluation={json.dumps(evaluation, ensure_ascii=False)}", flush=True)
    print("inflection_watchlist", flush=True)
    for row in watchlist.itertuples():
        print(
            f"{row.watch_rank:>2} {row.symbol:<8} score={row.inflection_score:5.1f} "
            f"revision={row.revision_score:5.1f} fundamental={row.fundamental_score:5.1f} "
            f"confirmation={row.confirmation_score:5.1f} reason={row.inflection_reason}",
            flush=True,
        )
    for name, path in paths.items():
        print(f"{name}_output={path}", flush=True)


if __name__ == "__main__":
    main()
