from datetime import date

import pandas as pd

from pit_radar.valuation_radar import (
    ValuationRadarConfig,
    _latest_fact,
    _latest_valuation_anchor,
    _sector_percentile,
    evaluate_matured_history,
    select_watchlists,
)


def test_lower_valuation_gets_higher_percentile() -> None:
    frame = pd.DataFrame(
        {"sector": ["Tech", "Tech", "Tech"], "pe": [10.0, 20.0, 40.0]}
    )

    result = _sector_percentile(frame, "pe", False, minimum_sector_size=1)

    assert result.iloc[0] == 1.0
    assert result.iloc[2] == 1 / 3


def test_watchlists_enforce_quality_and_valuation_gates() -> None:
    radar = pd.DataFrame(
        [
            {
                "security_id": 1,
                "eligible": True,
                "cheapness_score": 90.0,
                "quality_score": 80.0,
                "expectation_support_score": 70.0,
                "value_trap_flag": False,
                "weak_balance_flag": False,
                "value_trough_score": 85.0,
                "expensiveness_score": 10.0,
                "own_history_premium_score": 20.0,
                "overvaluation_score": 20.0,
                "data_coverage": 1.0,
                "market_cap": 10_000.0,
            },
            {
                "security_id": 2,
                "eligible": True,
                "cheapness_score": 95.0,
                "quality_score": 20.0,
                "expectation_support_score": 70.0,
                "value_trap_flag": False,
                "weak_balance_flag": False,
                "value_trough_score": 90.0,
                "expensiveness_score": 5.0,
                "own_history_premium_score": 10.0,
                "overvaluation_score": 30.0,
                "data_coverage": 1.0,
                "market_cap": 10_000.0,
            },
            {
                "security_id": 3,
                "eligible": True,
                "cheapness_score": 10.0,
                "quality_score": 60.0,
                "expectation_support_score": 30.0,
                "value_trap_flag": False,
                "weak_balance_flag": False,
                "value_trough_score": 25.0,
                "expensiveness_score": 90.0,
                "own_history_premium_score": 80.0,
                "overvaluation_score": 88.0,
                "data_coverage": 1.0,
                "market_cap": 10_000.0,
            },
        ]
    )
    config = ValuationRadarConfig(watchlist_size=2)

    value, overvalued = select_watchlists(radar, config)

    assert value["security_id"].tolist() == [1]
    assert overvalued["security_id"].tolist() == [3]
    assert set(value["security_id"]).isdisjoint(overvalued["security_id"])


def test_latest_period_is_used_instead_of_summing_cumulative_quarters() -> None:
    frame = pd.DataFrame(
        {
            "financial_fact_id": [1, 2],
            "security_id": [7, 7],
            "period_type": ["quarter", "quarter"],
            "fiscal_period_end": [date(2026, 2, 28), date(2026, 5, 31)],
            "fetched_at": pd.to_datetime(
                ["2026-03-10T00:00:00Z", "2026-06-10T00:00:00Z"]
            ),
            "revenue": [20.0, 35.0],
        }
    )

    latest = _latest_fact(frame, ["revenue"])

    assert latest.loc[0, "revenue"] == 35.0


def test_latest_valuation_anchor_joins_same_reported_period() -> None:
    common = {
        "financial_fact_id": [1, 2],
        "security_id": [7, 7],
        "period_type": ["quarter", "quarter"],
        "fiscal_period_end": [date(2026, 2, 28), date(2026, 5, 31)],
        "fetched_at": pd.to_datetime(
            ["2026-03-10T00:00:00Z", "2026-06-10T00:00:00Z"]
        ),
    }
    ratios = pd.DataFrame(
        {
            **common,
            "historical_pe": [20.0, 15.0],
            "historical_pfcf": [25.0, 18.0],
            "historical_ps": [5.0, 4.0],
            "historical_pb": [8.0, 7.0],
        }
    )
    key_metrics = pd.DataFrame(
        {
            **common,
            "historical_ev_to_ebitda": [22.0, 16.0],
            "reference_market_cap": [100.0, 120.0],
            "reference_enterprise_value": [110.0, 130.0],
        }
    )

    anchor = _latest_valuation_anchor(ratios, key_metrics)

    assert anchor.loc[0, "valuation_anchor_period_end"] == date(2026, 5, 31)
    assert anchor.loc[0, "valuation_anchor_pe"] == 15.0
    assert anchor.loc[0, "valuation_anchor_market_cap"] == 120.0


def test_forward_evaluation_stays_unavailable_without_history(tmp_path) -> None:
    bars = pd.DataFrame(
        columns=[
            "daily_bar_id",
            "security_id",
            "trade_date",
            "close",
            "fetched_at",
            "recorded_at",
        ]
    )

    result = evaluate_matured_history(tmp_path, bars, ValuationRadarConfig())

    assert result["horizons"]["20"]["matured_signal_dates"] == 0
    assert result["horizons"]["60"]["status"] == "insufficient_matured_signals"
