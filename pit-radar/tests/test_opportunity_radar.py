from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from pit_radar.opportunity_radar import (
    MODEL_FEATURES,
    RadarConfig,
    build_radar_dataset,
    decision_cutoff,
    evaluate_deployment_gate,
    fit_weighted_ridge,
    next_weekday,
)


def test_decision_cutoff_is_pre_open_in_new_york():
    cutoff = decision_cutoff(date(2026, 7, 31), RadarConfig())
    assert cutoff.isoformat() == "2026-07-31T13:29:00+00:00"


def test_next_weekday_skips_weekend():
    assert next_weekday(date(2026, 7, 31)) == date(2026, 8, 3)


def test_dataset_rejects_price_revision_fetched_after_cutoff():
    bars = pd.DataFrame(
        [
            _bar(1, "AAA", "2026-07-27", 10.0, "2026-07-27T23:30:00Z", 1),
            _bar(2, "BBB", "2026-07-27", 20.0, "2026-07-27T23:30:00Z", 2),
            _bar(1, "AAA", "2026-07-28", 11.0, "2026-07-28T23:30:00Z", 3),
            _bar(2, "BBB", "2026-07-28", 19.0, "2026-07-28T23:30:00Z", 4),
            _bar(1, "AAA", "2026-07-28", 999.0, "2026-07-29T14:00:00Z", 5),
            _bar(1, "AAA", "2026-07-29", 12.0, "2026-07-29T23:30:00Z", 6),
            _bar(2, "BBB", "2026-07-29", 21.0, "2026-07-29T23:30:00Z", 7),
        ]
    )
    bars["trade_date"] = pd.to_datetime(bars["trade_date"]).dt.date
    bars["fetched_at"] = pd.to_datetime(bars["fetched_at"], utc=True)
    bars["recorded_at"] = pd.to_datetime(bars["recorded_at"], utc=True)
    estimates = _empty_estimates()
    analysts = _empty_analysts()
    config = RadarConfig(
        minimum_universe_size=1,
        minimum_price=0,
        minimum_dollar_volume=0,
        minimum_label_coverage=1.0,
    )

    dataset, audit = build_radar_dataset(bars, estimates, analysts, config)

    row = dataset.loc[
        (dataset["signal_date"] == date(2026, 7, 28)) & (dataset["symbol"] == "AAA")
    ].iloc[0]
    assert row["close"] == 11.0
    assert not bool(row["asof_violation"])
    assert audit["feature_asof_violations"].sum() == 0


def test_weighted_ridge_is_finite_and_uses_multiple_dates():
    rows = []
    for day, direction in ((date(2026, 7, 20), 1.0), (date(2026, 7, 21), -1.0)):
        for security_id in range(1, 6):
            row = {
                "signal_date": day,
                "security_id": security_id,
                "label_return": direction * security_id / 1000.0,
            }
            for index, feature in enumerate(MODEL_FEATURES):
                row[f"z__{feature}"] = (security_id - 3) * (1 if index % 2 == 0 else -1)
            rows.append(row)
    frame = pd.DataFrame(rows)

    model = fit_weighted_ridge(frame, RadarConfig(ridge_alpha=10.0))

    assert model.train_dates == 2
    assert model.train_rows == 10
    assert np.isfinite(model.intercept)
    assert all(np.isfinite(value) for value in model.coefficients.values())


def test_deployment_gate_blocks_short_or_negative_backtest():
    frame = pd.DataFrame(
        [
            {
                "signal_date": date(2026, 7, 20),
                "security_id": 1,
                "label_return": 0.01,
                **{f"z__{feature}": 0.0 for feature in MODEL_FEATURES},
            }
        ]
    )
    model = fit_weighted_ridge(frame, RadarConfig())
    gate = evaluate_deployment_gate(
        {
            "backtest_days": 7,
            "cumulative_net_return": -0.01,
            "cumulative_excess_return": 0.01,
            "average_information_coefficient": -0.02,
        },
        model,
        feature_asof_violations=0,
    )

    assert gate["status"] == "research_only"
    assert not gate["passed"]
    assert "minimum_60_training_dates" in gate["failed_checks"]
    assert "positive_rank_ic" in gate["failed_checks"]


def _bar(
    security_id: int,
    symbol: str,
    trade_date: str,
    close: float,
    fetched_at: str,
    daily_bar_id: int,
) -> dict[str, object]:
    return {
        "daily_bar_id": daily_bar_id,
        "security_id": security_id,
        "symbol": symbol,
        "company_name": symbol,
        "sector": "Technology",
        "industry": "Test",
        "trade_date": trade_date,
        "open": close * 0.99,
        "high": close * 1.01,
        "low": close * 0.98,
        "close": close,
        "volume": 1_000_000.0,
        "fetched_at": fetched_at,
        "recorded_at": fetched_at,
    }


def _empty_estimates() -> pd.DataFrame:
    frame = pd.DataFrame(
        columns=[
            "estimate_id",
            "security_id",
            "fiscal_period_end",
            "period_type",
            "eps_mean",
            "eps_high",
            "eps_low",
            "analyst_count_eps",
            "revenue_mean",
            "revenue_high",
            "revenue_low",
            "analyst_count_revenue",
            "fetched_at",
            "recorded_at",
        ]
    )
    frame["fiscal_period_end"] = pd.to_datetime(frame["fiscal_period_end"]).dt.date
    frame["fetched_at"] = pd.to_datetime(frame["fetched_at"], utc=True)
    frame["recorded_at"] = pd.to_datetime(frame["recorded_at"], utc=True)
    return frame


def _empty_analysts() -> pd.DataFrame:
    frame = pd.DataFrame(
        columns=[
            "analyst_snapshot_id",
            "security_id",
            "target_mean",
            "target_high",
            "target_low",
            "strong_buy_count",
            "buy_count",
            "hold_count",
            "sell_count",
            "strong_sell_count",
            "fetched_at",
            "recorded_at",
        ]
    )
    frame["fetched_at"] = pd.to_datetime(frame["fetched_at"], utc=True)
    frame["recorded_at"] = pd.to_datetime(frame["recorded_at"], utc=True)
    return frame
