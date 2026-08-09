#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pit_radar.db.session import create_db_engine
from pit_radar.opportunity_radar import (
    RadarConfig,
    build_radar_dataset,
    evaluate_deployment_gate,
    load_pit_frames,
    train_latest_radar,
    walk_forward_backtest,
    write_radar_outputs,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train a strict point-in-time stock opportunity radar and run an expanding walk-forward backtest."
    )
    parser.add_argument("--output-dir", default="data/radar")
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--minimum-train-dates", type=int, default=4)
    parser.add_argument("--minimum-universe-size", type=int, default=1000)
    parser.add_argument("--minimum-label-coverage", type=float, default=0.90)
    parser.add_argument("--minimum-price", type=float, default=3.0)
    parser.add_argument("--minimum-dollar-volume", type=float, default=5_000_000.0)
    parser.add_argument("--transaction-cost-bps", type=float, default=20.0)
    parser.add_argument("--ridge-alpha", type=float, default=100.0)
    args = parser.parse_args()

    config = RadarConfig(
        top_k=args.top_k,
        minimum_train_dates=args.minimum_train_dates,
        minimum_universe_size=args.minimum_universe_size,
        minimum_label_coverage=args.minimum_label_coverage,
        minimum_price=args.minimum_price,
        minimum_dollar_volume=args.minimum_dollar_volume,
        transaction_cost_bps=args.transaction_cost_bps,
        ridge_alpha=args.ridge_alpha,
    )
    engine = create_db_engine()
    try:
        bars, estimates, analysts = load_pit_frames(engine)
        dataset, audit = build_radar_dataset(bars, estimates, analysts, config)
    finally:
        engine.dispose()

    backtest, metrics = walk_forward_backtest(dataset, config)
    radar, model = train_latest_radar(dataset, config)
    paths = write_radar_outputs(
        Path(args.output_dir),
        radar,
        backtest,
        audit,
        model,
        metrics,
        config,
    )
    gate = evaluate_deployment_gate(
        metrics,
        model,
        int(audit["feature_asof_violations"].sum()),
    )

    print(
        f"signal_date={radar['signal_date'].max()} entry_date={radar['entry_date'].iloc[0]} "
        f"candidates={len(radar)} train_dates={model.train_dates} train_rows={model.train_rows}",
        flush=True,
    )
    print(f"backtest={json.dumps(metrics, ensure_ascii=False)}", flush=True)
    print(f"deployment_gate={json.dumps(gate, ensure_ascii=False)}", flush=True)
    print("top_candidates", flush=True)
    for row in radar.head(config.top_k).itertuples():
        print(
            f"{row.rank:>2} {row.symbol:<8} score={row.radar_score:5.1f} "
            f"predicted_excess_bps={row.predicted_excess_return * 10_000:7.2f} "
            f"coverage={row.feature_coverage:.0%} reason={row.reason}",
            flush=True,
        )
    for name, path in paths.items():
        print(f"{name}_output={path}", flush=True)


if __name__ == "__main__":
    main()
