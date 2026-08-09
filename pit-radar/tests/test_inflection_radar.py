from __future__ import annotations

from datetime import date

import pandas as pd

from pit_radar.inflection_radar import (
    InflectionRadarConfig,
    _scaled_change,
    _score_inflection_radar,
    evaluate_forward_labels,
    select_inflection_watchlist,
)


def test_scaled_revision_handles_negative_to_positive_inflection() -> None:
    current = pd.Series([0.50, 110.0])
    prior = pd.Series([-0.25, 100.0])

    result = _scaled_change(current, prior, 0.10)

    assert result.iloc[0] == 3.0
    assert result.iloc[1] == 0.10


def test_revision_and_confirmation_raise_inflection_rank() -> None:
    frame = pd.DataFrame(
        [
            _score_row(1, eps_revision=0.30, relative_return=0.20),
            _score_row(2, eps_revision=-0.20, relative_return=-0.10),
        ]
    )
    config = InflectionRadarConfig(minimum_sector_size=1)

    scored = _score_inflection_radar(frame, config).set_index("security_id")

    assert scored.loc[1, "revision_score"] > scored.loc[2, "revision_score"]
    assert scored.loc[1, "confirmation_score"] > scored.loc[2, "confirmation_score"]
    assert scored.loc[1, "inflection_score"] > scored.loc[2, "inflection_score"]


def test_sparse_core_components_do_not_receive_scores() -> None:
    sparse = _score_row(1, eps_revision=0.30, relative_return=0.20)
    for column in (
        "q_revenue_revision_20d",
        "fy_eps_revision_20d",
        "target_revision_20d",
        "eps_revision",
    ):
        sparse[column] = None
    for column in (
        "eps_growth",
        "free_cash_flow_growth",
        "revenue_growth_acceleration",
        "eps_growth_acceleration",
        "operating_margin",
        "fcf_margin",
        "roic",
    ):
        sparse[column] = None

    scored = _score_inflection_radar(
        pd.DataFrame([sparse]), InflectionRadarConfig(minimum_sector_size=1)
    ).iloc[0]

    assert pd.isna(scored["revision_score"])
    assert pd.isna(scored["fundamental_score"])


def test_watchlist_enforces_eligibility_and_rank() -> None:
    radar = pd.DataFrame(
        [
            {"security_id": 1, "eligible": True, "inflection_score": 80.0, "inflection_data_coverage": 0.8, "dollar_volume": 10.0},
            {"security_id": 2, "eligible": False, "inflection_score": 95.0, "inflection_data_coverage": 1.0, "dollar_volume": 20.0},
            {"security_id": 3, "eligible": True, "inflection_score": 70.0, "inflection_data_coverage": 0.9, "dollar_volume": 30.0},
        ]
    )

    result = select_inflection_watchlist(
        radar, InflectionRadarConfig(watchlist_size=2)
    )

    assert result["security_id"].tolist() == [1, 3]
    assert result["watch_rank"].tolist() == [1, 2]


def test_forward_labels_are_sector_relative(tmp_path) -> None:
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    snapshot = pd.DataFrame(
        [
            {"security_id": 1, "symbol": "AAA", "sector": "Tech", "signal_date": "2026-01-05", "eligible": True, "inflection_score": 90.0},
            {"security_id": 2, "symbol": "BBB", "sector": "Tech", "signal_date": "2026-01-05", "eligible": True, "inflection_score": 50.0},
            {"security_id": 3, "symbol": "CCC", "sector": "Tech", "signal_date": "2026-01-05", "eligible": True, "inflection_score": 10.0},
        ]
    )
    snapshot.to_csv(
        history_dir / "inflection_scores_2026-01-05_20260105T230000Z.csv", index=False
    )
    rows = []
    closes = {
        1: [10.0, 10.5, 12.0],
        2: [10.0, 10.1, 11.0],
        3: [10.0, 9.9, 10.0],
    }
    for security_id, values in closes.items():
        for index, (trade_date, close) in enumerate(
            zip(("2026-01-05", "2026-01-06", "2026-01-07"), values), start=1
        ):
            rows.append(
                {
                    "daily_bar_id": security_id * 10 + index,
                    "security_id": security_id,
                    "trade_date": trade_date,
                    "close": close,
                    "fetched_at": f"{trade_date}T23:00:00Z",
                    "recorded_at": f"{trade_date}T23:00:00Z",
                }
            )
    bars = pd.DataFrame(rows)
    bars["trade_date"] = pd.to_datetime(bars["trade_date"]).dt.date
    bars["fetched_at"] = pd.to_datetime(bars["fetched_at"], utc=True)
    bars["recorded_at"] = pd.to_datetime(bars["recorded_at"], utc=True)
    config = InflectionRadarConfig(
        watchlist_size=1, minimum_sector_size=1, forward_horizons=(2,)
    )

    labels, evaluation = evaluate_forward_labels(history_dir, bars, config)

    top = labels.loc[labels["security_id"] == 1].iloc[0]
    assert round(top["forward_return"], 6) == 0.20
    assert round(top["forward_excess_return"], 6) == 0.10
    assert evaluation["horizons"]["2"]["matured_signal_dates"] == 1
    assert round(evaluation["horizons"]["2"]["average_watchlist_excess_return"], 6) == 0.10


def _score_row(
    security_id: int,
    eps_revision: float,
    relative_return: float,
) -> dict[str, object]:
    return {
        "security_id": security_id,
        "sector": "Technology",
        "q_eps_revision_20d": eps_revision,
        "q_revenue_revision_20d": eps_revision / 2,
        "fy_eps_revision_20d": eps_revision / 2,
        "target_revision_20d": eps_revision / 3,
        "eps_revision": eps_revision / 2,
        "revenue_growth": eps_revision,
        "eps_growth": eps_revision,
        "free_cash_flow_growth": eps_revision,
        "revenue_growth_acceleration": eps_revision,
        "eps_growth_acceleration": eps_revision,
        "operating_margin": 0.20 + eps_revision / 10,
        "fcf_margin": 0.10 + eps_revision / 10,
        "roic": 0.15 + eps_revision / 10,
        "sector_relative_return_20d": relative_return,
        "sector_relative_return_60d": relative_return,
        "price_return_120d": relative_return,
        "volume_ratio_20d": 1.0 + relative_return,
        "distance_from_52w_high": -0.10 + relative_return / 10,
        "cheapness_score": 60.0,
        "own_history_discount_score": 60.0,
        "forward_pe": 15.0,
        "target_upside": 0.30,
        "recommendation_score": 0.50,
        "fmp_rating_score": 4.0,
        "sector_revision_breadth": 0.60,
        "volatility_20d": 0.02,
        "net_debt_to_operating_income": 1.0,
        "value_trap_flag": False,
        "weak_balance_flag": False,
    }
