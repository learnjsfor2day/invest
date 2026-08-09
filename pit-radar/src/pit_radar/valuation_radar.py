from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pit_radar import scoring
from pit_radar.scoring import (
    ensure_utc as _ensure_utc,
    global_percentile as _global_percentile,
    mean_or_none as _mean_or_none,
    positive_ratio as _positive_ratio,
    ratio as _ratio,
    sector_percentile as _sector_percentile,
    top_components as _top_components,
    weighted_score as _weighted_score,
)


@dataclass(frozen=True)
class ValuationRadarConfig:
    watchlist_size: int = 30
    minimum_price: float = 3.0
    minimum_market_cap: float = 300_000_000.0
    minimum_dollar_volume: float = 5_000_000.0
    minimum_data_coverage: float = 0.45
    minimum_sector_size: int = 12
    minimum_value_cheapness_score: float = 55.0
    minimum_value_quality_score: float = 50.0
    minimum_value_expectation_score: float = 35.0
    minimum_overvaluation_expensiveness_score: float = 65.0
    minimum_overvaluation_history_premium_score: float = 70.0
    history_years: int = 5
    forward_horizons: tuple[int, ...] = (20, 60)


VALUE_COMPONENT_WEIGHTS = {
    "cheapness_score": 0.40,
    "own_history_discount_score": 0.20,
    "quality_score": 0.20,
    "expectation_support_score": 0.15,
    "price_trough_score": 0.05,
}

OVERVALUATION_COMPONENT_WEIGHTS = {
    "expensiveness_score": 0.40,
    "own_history_premium_score": 0.20,
    "weak_quality_score": 0.15,
    "expectation_fragility_score": 0.15,
    "price_heat_score": 0.10,
}


def build_valuation_radar(
    engine: Engine,
    as_of: datetime,
    config: ValuationRadarConfig,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    as_of = _ensure_utc(as_of)
    frames = _load_frames(engine, as_of)
    radar = _assemble_features(frames, as_of, config)
    radar = _score_radar(radar, config)
    audit = _audit_payload(radar, frames, as_of, config)
    if audit["feature_asof_violations"]:
        raise AssertionError("Valuation radar contains data fetched after the as-of cutoff.")
    return radar, audit


def load_visible_bars(engine: Engine, as_of: datetime) -> pd.DataFrame:
    """Load price observations visible by cutoff for forward-label evaluation."""
    as_of = _ensure_utc(as_of)
    bars = pd.read_sql_query(
        text(
            """
            SELECT d.daily_bar_id,d.security_id,d.trade_date,
                   CAST(d.close AS REAL) AS close,d.fetched_at,d.recorded_at
            FROM pit.daily_market_bar d
            WHERE d.fetched_at <= :cutoff AND d.close IS NOT NULL
            """
        ),
        engine,
        params={"cutoff": as_of.replace(tzinfo=None)},
    )
    _normalize_common_frame(bars)
    bars["trade_date"] = pd.to_datetime(bars["trade_date"]).dt.date
    return bars


def _load_frames(engine: Engine, as_of: datetime) -> dict[str, pd.DataFrame]:
    cutoff = as_of.replace(tzinfo=None)
    params = {"cutoff": cutoff}
    frames = {
        "bars": pd.read_sql_query(
            text(
                """
                SELECT d.daily_bar_id,d.security_id,s.primary_ticker AS symbol,
                       s.company_name,s.sector,s.industry,s.country,d.trade_date,
                       CAST(d.open AS REAL) AS open,CAST(d.high AS REAL) AS high,
                       CAST(d.low AS REAL) AS low,CAST(d.close AS REAL) AS close,
                       CAST(d.volume AS REAL) AS volume,d.fetched_at,d.recorded_at
                FROM pit.daily_market_bar d
                JOIN core.security s ON s.security_id=d.security_id
                WHERE d.fetched_at <= :cutoff AND d.close IS NOT NULL
                """
            ),
            engine,
            params=params,
        ),
        "metrics": pd.read_sql_query(
            text(
                """
                SELECT observation_id,security_id,metric_code,
                       CAST(value_numeric AS REAL) AS value_numeric,fetched_at,recorded_at
                FROM pit.metric_observation
                WHERE fetched_at <= :cutoff
                  AND metric_code IN ('market_cap','fmp_rating_overall_score')
                """
            ),
            engine,
            params=params,
        ),
        "estimates": pd.read_sql_query(
            text(
                """
                SELECT estimate_id,security_id,fiscal_period_end,period_type,
                       CAST(eps_mean AS REAL) AS eps_mean,
                       CAST(revenue_mean AS REAL) AS revenue_mean,
                       analyst_count_eps,analyst_count_revenue,fetched_at,recorded_at
                FROM pit.estimate_snapshot
                WHERE fetched_at <= :cutoff
                """
            ),
            engine,
            params=params,
        ),
        "analysts": pd.read_sql_query(
            text(
                """
                SELECT analyst_snapshot_id,security_id,CAST(target_mean AS REAL) AS target_mean,
                       strong_buy_count,buy_count,hold_count,sell_count,strong_sell_count,
                       fetched_at,recorded_at
                FROM pit.analyst_snapshot
                WHERE fetched_at <= :cutoff
                """
            ),
            engine,
            params=params,
        ),
        "income": _load_fact_frame(
            engine,
            cutoff,
            "income_statement",
            {
                "reported_currency": "reportedCurrency",
                "revenue": "revenue",
                "gross_profit": "grossProfit",
                "operating_income": "operatingIncome",
                "net_income": "netIncome",
            },
        ),
        "cash_flow": _load_fact_frame(
            engine,
            cutoff,
            "cash_flow",
            {
                "reported_currency": "reportedCurrency",
                "operating_cash_flow": "operatingCashFlow",
                "free_cash_flow": "freeCashFlow",
            },
        ),
        "balance": _load_fact_frame(
            engine,
            cutoff,
            "balance_sheet",
            {
                "reported_currency": "reportedCurrency",
                "cash_and_investments": "cashAndShortTermInvestments",
                "total_debt": "totalDebt",
                "stockholders_equity": "totalStockholdersEquity",
                "total_assets": "totalAssets",
            },
        ),
        "growth": _load_fact_frame(
            engine,
            cutoff,
            "financial_growth",
            {
                "revenue_growth": "revenueGrowth",
                "eps_growth": "epsgrowth",
                "free_cash_flow_growth": "freeCashFlowGrowth",
            },
        ),
        "key_metrics": _load_fact_frame(
            engine,
            cutoff,
            "key_metrics",
            {
                "roic": "returnOnInvestedCapital",
                "income_quality": "incomeQuality",
                "historical_ev_to_ebitda": "evToEBITDA",
                "reference_market_cap": "marketCap",
                "reference_enterprise_value": "enterpriseValue",
            },
        ),
        "ratios": _load_fact_frame(
            engine,
            cutoff,
            "ratios",
            {
                "historical_pe": "priceToEarningsRatio",
                "historical_pb": "priceToBookRatio",
                "historical_ps": "priceToSalesRatio",
                "historical_pfcf": "priceToFreeCashFlowRatio",
            },
        ),
        "scores": _load_fact_frame(
            engine,
            cutoff,
            "financial_scores",
            {
                "altman_z": "altmanZScore",
                "piotroski": "piotroskiScore",
            },
        ),
    }
    for name in ("bars", "metrics", "estimates", "analysts"):
        _normalize_common_frame(frames[name])
    for name in (
        "income",
        "cash_flow",
        "balance",
        "growth",
        "key_metrics",
        "ratios",
        "scores",
    ):
        _normalize_fact_frame(frames[name])
    frames["estimates"]["fiscal_period_end"] = pd.to_datetime(
        frames["estimates"]["fiscal_period_end"]
    ).dt.date
    frames["bars"]["trade_date"] = pd.to_datetime(frames["bars"]["trade_date"]).dt.date
    return frames


def _load_fact_frame(
    engine: Engine,
    cutoff: datetime,
    dataset_code: str,
    fields: dict[str, str],
) -> pd.DataFrame:
    extracted = ",".join(
        f"CAST(json_extract(value_json, '$.{json_key}') AS REAL) AS {column}"
        if column != "reported_currency"
        else f"json_extract(value_json, '$.{json_key}') AS {column}"
        for column, json_key in fields.items()
    )
    query = text(
        f"""
        SELECT financial_fact_id,security_id,period_type,fiscal_period_end,
               accepted_at,fetched_at,recorded_at,{extracted}
        FROM pit.financial_fact_snapshot
        WHERE dataset_code=:dataset_code
          AND fetched_at <= :cutoff
          AND (accepted_at IS NULL OR accepted_at <= :cutoff)
        """
    )
    return pd.read_sql_query(
        query,
        engine,
        params={"dataset_code": dataset_code, "cutoff": cutoff},
    )


def _normalize_common_frame(frame: pd.DataFrame) -> None:
    for column in ("fetched_at", "recorded_at"):
        if column in frame:
            frame[column] = pd.to_datetime(frame[column], utc=True)


def _normalize_fact_frame(frame: pd.DataFrame) -> None:
    _normalize_common_frame(frame)
    frame["accepted_at"] = pd.to_datetime(frame["accepted_at"], utc=True)
    frame["fiscal_period_end"] = pd.to_datetime(frame["fiscal_period_end"]).dt.date


def _assemble_features(
    frames: dict[str, pd.DataFrame],
    as_of: datetime,
    config: ValuationRadarConfig,
) -> pd.DataFrame:
    bars = _dedupe_bars(frames["bars"])
    broad_counts = bars.groupby("trade_date")["security_id"].nunique()
    broad_dates = broad_counts.loc[broad_counts >= 1000]
    if broad_dates.empty:
        raise ValueError("No broad-universe price date is available before the as-of cutoff.")
    signal_date = broad_dates.index.max()
    history = bars.loc[bars["trade_date"] <= signal_date].copy()
    current = history.loc[history["trade_date"] == signal_date].copy()
    current = current.sort_values(["security_id", "fetched_at"]).drop_duplicates(
        "security_id", keep="last"
    )
    price_features = _price_features(history, signal_date)
    current = current.merge(price_features, on="security_id", how="left")
    current["signal_date"] = signal_date
    current["as_of_utc"] = pd.Timestamp(as_of)
    current["dollar_volume"] = current["close"] * current["volume"]

    market_cap = _latest_metric(frames["metrics"], "market_cap", "market_cap")
    fmp_score = _latest_metric(
        frames["metrics"], "fmp_rating_overall_score", "fmp_rating_score"
    )
    current = current.merge(market_cap, on="security_id", how="left")
    current = current.merge(fmp_score, on="security_id", how="left")

    # FMP quarterly statements can contain fiscal year-to-date values. Use the
    # latest disclosed period for margins/quality instead of summing quarters.
    latest_income = _latest_fact(
        frames["income"],
        ["reported_currency", "revenue", "gross_profit", "operating_income", "net_income"],
    ).rename(columns={"reported_currency": "income_currency"})
    latest_cash = _latest_fact(
        frames["cash_flow"],
        ["reported_currency", "operating_cash_flow", "free_cash_flow"],
    ).rename(columns={"reported_currency": "cash_flow_currency"})
    latest_balance = _latest_fact(
        frames["balance"],
        [
            "reported_currency",
            "cash_and_investments",
            "total_debt",
            "stockholders_equity",
            "total_assets",
        ],
    )
    latest_growth = _latest_fact(
        frames["growth"], ["revenue_growth", "eps_growth", "free_cash_flow_growth"]
    )
    latest_key = _latest_fact(frames["key_metrics"], ["roic", "income_quality"])
    latest_scores = _latest_fact(frames["scores"], ["altman_z", "piotroski"])
    valuation_anchor = _latest_valuation_anchor(frames["ratios"], frames["key_metrics"])
    historical = _historical_valuation_medians(
        frames["ratios"], frames["key_metrics"], config.history_years
    )
    estimates = _estimate_features(frames["estimates"], signal_date)
    analysts = _analyst_features(frames["analysts"])

    for feature_frame in (
        latest_income,
        latest_cash,
        latest_balance,
        latest_growth,
        latest_key,
        latest_scores,
        valuation_anchor,
        historical,
        estimates,
        analysts,
    ):
        current = current.merge(feature_frame, on="security_id", how="left")

    current["enterprise_value"] = (
        current["market_cap"]
        + current["total_debt"].fillna(0)
        - current["cash_and_investments"].fillna(0)
    )
    market_cap_scale = _positive_ratio(
        current["market_cap"], current["valuation_anchor_market_cap"]
    )
    enterprise_value_scale = _positive_ratio(
        current["enterprise_value"], current["valuation_anchor_enterprise_value"]
    )
    # Re-anchor FMP's most recent reported valuation ratios to the current PIT
    # market cap. This avoids treating cumulative 10-Q statement values as
    # independent quarters while keeping fundamentals frozen at disclosure.
    current["pe"] = current["valuation_anchor_pe"] * market_cap_scale
    current["pfcf"] = current["valuation_anchor_pfcf"] * market_cap_scale
    current["ps"] = current["valuation_anchor_ps"] * market_cap_scale
    current["pb"] = current["valuation_anchor_pb"] * market_cap_scale
    current["ev_to_ebitda"] = (
        current["valuation_anchor_ev_to_ebitda"] * enterprise_value_scale
    )
    current["ev_to_operating_income"] = _positive_ratio(
        current["enterprise_value"], current["operating_income"]
    )
    current["fcf_yield"] = _positive_ratio(
        pd.Series(1.0, index=current.index), current["pfcf"]
    )
    current["operating_margin"] = _ratio(current["operating_income"], current["revenue"])
    current["fcf_margin"] = _ratio(current["free_cash_flow"], current["revenue"])
    current["net_debt_to_operating_income"] = _ratio(
        current["total_debt"].fillna(0) - current["cash_and_investments"].fillna(0),
        current["operating_income"],
    )
    current["target_upside"] = _ratio(current["target_mean"], current["close"]) - 1.0
    current["pe_vs_history"] = _ratio(current["pe"], current["median_historical_pe"])
    current["pfcf_vs_history"] = _ratio(current["pfcf"], current["median_historical_pfcf"])
    current["ps_vs_history"] = _ratio(current["ps"], current["median_historical_ps"])
    current["pb_vs_history"] = _ratio(current["pb"], current["median_historical_pb"])
    current["ev_to_ebitda_vs_history"] = _ratio(
        current["ev_to_ebitda"], current["median_historical_ev_to_ebitda"]
    )
    current["currency_compatible"] = (
        current["income_currency"].eq("USD") & current["cash_flow_currency"].eq("USD")
    )
    raw_coverage = [
        "market_cap",
        "revenue",
        "net_income",
        "free_cash_flow",
        "stockholders_equity",
        "pe",
        "pfcf",
        "ps",
        "pb",
        "roic",
        "piotroski",
        "revenue_growth",
        "eps_revision",
        "target_upside",
    ]
    current["data_coverage"] = current[raw_coverage].notna().mean(axis=1)
    current["eligible"] = (
        current["currency_compatible"]
        & (current["close"] >= config.minimum_price)
        & (current["market_cap"] >= config.minimum_market_cap)
        & (current["dollar_volume"] >= config.minimum_dollar_volume)
        & (current["data_coverage"] >= config.minimum_data_coverage)
    )
    return current


def _dedupe_bars(bars: pd.DataFrame) -> pd.DataFrame:
    return (
        bars.sort_values(
            ["security_id", "trade_date", "fetched_at", "recorded_at", "daily_bar_id"]
        )
        .drop_duplicates(["security_id", "trade_date"], keep="last")
        .sort_values(["security_id", "trade_date"])
    )


def _price_features(history: pd.DataFrame, signal_date: date) -> pd.DataFrame:
    history = history.sort_values(["security_id", "trade_date"]).copy()
    groups = history.groupby("security_id", sort=False)
    history["price_history_days"] = groups["close"].transform("count")
    history["history_high"] = groups["close"].cummax()
    history["price_drawdown"] = history["close"] / history["history_high"] - 1.0
    history["price_return_5d"] = groups["close"].pct_change(5, fill_method=None)
    history["price_return_10d"] = groups["close"].pct_change(10, fill_method=None)
    return history.loc[
        history["trade_date"] == signal_date,
        [
            "security_id",
            "price_history_days",
            "price_drawdown",
            "price_return_5d",
            "price_return_10d",
        ],
    ].drop_duplicates("security_id", keep="last")


def _latest_metric(metrics: pd.DataFrame, metric_code: str, output_name: str) -> pd.DataFrame:
    part = metrics.loc[metrics["metric_code"] == metric_code].copy()
    part = part.sort_values(
        ["security_id", "fetched_at", "recorded_at", "observation_id"]
    ).drop_duplicates("security_id", keep="last")
    return part.rename(
        columns={"value_numeric": output_name, "fetched_at": f"{output_name}_fetched_at"}
    )[["security_id", output_name, f"{output_name}_fetched_at"]]


def _latest_fact(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["security_id", *columns])
    part = _dedupe_facts(frame)
    part = part.sort_values(
        ["security_id", "fiscal_period_end", "fetched_at", "financial_fact_id"]
    ).drop_duplicates("security_id", keep="last")
    return part[["security_id", *columns]].reset_index(drop=True)


def _dedupe_facts(frame: pd.DataFrame) -> pd.DataFrame:
    return (
        frame.sort_values(
            ["security_id", "period_type", "fiscal_period_end", "fetched_at", "financial_fact_id"]
        )
        .drop_duplicates(["security_id", "period_type", "fiscal_period_end"], keep="last")
    )


def _historical_valuation_medians(
    ratios: pd.DataFrame,
    key_metrics: pd.DataFrame,
    history_years: int,
) -> pd.DataFrame:
    ratio_columns = ["historical_pe", "historical_pb", "historical_ps", "historical_pfcf"]
    annual = _dedupe_facts(ratios).loc[lambda item: item["period_type"] == "fiscal_year"].copy()
    annual = annual.sort_values(["security_id", "fiscal_period_end"])
    annual["history_rank"] = annual.groupby("security_id").cumcount(ascending=False)
    annual = annual.loc[annual["history_rank"] < history_years]
    for column in ratio_columns:
        annual[column] = annual[column].where(annual[column] > 0)
    medians = annual.groupby("security_id")[ratio_columns].median().rename(
        columns={column: f"median_{column}" for column in ratio_columns}
    )

    key = _dedupe_facts(key_metrics).loc[
        lambda item: item["period_type"] == "fiscal_year"
    ].copy()
    key = key.sort_values(["security_id", "fiscal_period_end"])
    key["history_rank"] = key.groupby("security_id").cumcount(ascending=False)
    key = key.loc[(key["history_rank"] < history_years) & (key["historical_ev_to_ebitda"] > 0)]
    ev = key.groupby("security_id")["historical_ev_to_ebitda"].median().rename(
        "median_historical_ev_to_ebitda"
    )
    return medians.join(ev, how="outer").reset_index()


def _latest_valuation_anchor(
    ratios: pd.DataFrame,
    key_metrics: pd.DataFrame,
) -> pd.DataFrame:
    if ratios.empty or key_metrics.empty:
        return pd.DataFrame(
            columns=[
                "security_id",
                "valuation_anchor_period_end",
                "valuation_anchor_market_cap",
                "valuation_anchor_enterprise_value",
                "valuation_anchor_pe",
                "valuation_anchor_pfcf",
                "valuation_anchor_ps",
                "valuation_anchor_pb",
                "valuation_anchor_ev_to_ebitda",
            ]
        )
    ratio_columns = [
        "security_id",
        "period_type",
        "fiscal_period_end",
        "historical_pe",
        "historical_pfcf",
        "historical_ps",
        "historical_pb",
    ]
    key_columns = [
        "security_id",
        "period_type",
        "fiscal_period_end",
        "historical_ev_to_ebitda",
        "reference_market_cap",
        "reference_enterprise_value",
    ]
    anchors = _dedupe_facts(ratios)[ratio_columns].merge(
        _dedupe_facts(key_metrics)[key_columns],
        on=["security_id", "period_type", "fiscal_period_end"],
        how="inner",
    )
    anchors = anchors.loc[anchors["reference_market_cap"] > 0].copy()
    anchors = anchors.sort_values(
        ["security_id", "fiscal_period_end"]
    ).drop_duplicates("security_id", keep="last")
    return anchors.rename(
        columns={
            "fiscal_period_end": "valuation_anchor_period_end",
            "reference_market_cap": "valuation_anchor_market_cap",
            "reference_enterprise_value": "valuation_anchor_enterprise_value",
            "historical_pe": "valuation_anchor_pe",
            "historical_pfcf": "valuation_anchor_pfcf",
            "historical_ps": "valuation_anchor_ps",
            "historical_pb": "valuation_anchor_pb",
            "historical_ev_to_ebitda": "valuation_anchor_ev_to_ebitda",
        }
    ).drop(columns=["period_type"]).reset_index(drop=True)


def _estimate_features(estimates: pd.DataFrame, signal_date: date) -> pd.DataFrame:
    quarter = estimates.loc[
        (estimates["period_type"] == "quarter")
        & (estimates["fiscal_period_end"] >= signal_date)
    ].copy()
    if quarter.empty:
        return pd.DataFrame(columns=["security_id", "eps_revision", "revenue_revision"])
    latest_period = quarter.groupby("security_id")["fiscal_period_end"].min().rename(
        "selected_period"
    )
    quarter = quarter.merge(latest_period, on="security_id")
    quarter = quarter.loc[quarter["fiscal_period_end"] == quarter["selected_period"]]
    quarter = quarter.sort_values(
        ["security_id", "fetched_at", "recorded_at", "estimate_id"]
    )
    quarter["previous_eps"] = quarter.groupby("security_id")["eps_mean"].shift(1)
    quarter["previous_revenue"] = quarter.groupby("security_id")["revenue_mean"].shift(1)
    latest = quarter.drop_duplicates("security_id", keep="last").copy()
    latest["eps_revision"] = _ratio(latest["eps_mean"], latest["previous_eps"]) - 1.0
    latest["revenue_revision"] = _ratio(
        latest["revenue_mean"], latest["previous_revenue"]
    ) - 1.0
    return latest.rename(
        columns={
            "fiscal_period_end": "next_q_period_end",
            "eps_mean": "next_q_eps_mean",
            "revenue_mean": "next_q_revenue_mean",
            "fetched_at": "estimate_fetched_at",
        }
    )[
        [
            "security_id",
            "next_q_period_end",
            "next_q_eps_mean",
            "next_q_revenue_mean",
            "eps_revision",
            "revenue_revision",
            "estimate_fetched_at",
        ]
    ]


def _analyst_features(analysts: pd.DataFrame) -> pd.DataFrame:
    if analysts.empty:
        return pd.DataFrame(columns=["security_id", "target_mean", "target_revision"])
    part = analysts.sort_values(
        ["security_id", "fetched_at", "recorded_at", "analyst_snapshot_id"]
    ).copy()
    part["previous_target"] = part.groupby("security_id")["target_mean"].shift(1)
    latest = part.drop_duplicates("security_id", keep="last").copy()
    latest["target_revision"] = _ratio(latest["target_mean"], latest["previous_target"]) - 1.0
    rating_total = latest[
        ["strong_buy_count", "buy_count", "hold_count", "sell_count", "strong_sell_count"]
    ].fillna(0).sum(axis=1)
    rating_value = (
        2 * latest["strong_buy_count"].fillna(0)
        + latest["buy_count"].fillna(0)
        - latest["sell_count"].fillna(0)
        - 2 * latest["strong_sell_count"].fillna(0)
    )
    latest["recommendation_score"] = rating_value.where(rating_total > 0) / rating_total.where(
        rating_total > 0
    )
    return latest.rename(columns={"fetched_at": "analyst_fetched_at"})[
        [
            "security_id",
            "target_mean",
            "target_revision",
            "recommendation_score",
            "analyst_fetched_at",
        ]
    ]


def _score_radar(frame: pd.DataFrame, config: ValuationRadarConfig) -> pd.DataFrame:
    output = frame.copy()
    output["sector"] = output["sector"].fillna("Unknown")
    valuation_ranks = []
    for column in ("pe", "pfcf", "ps", "pb", "ev_to_ebitda"):
        rank_name = f"cheap__{column}"
        output[rank_name] = _sector_percentile(output, column, False, config.minimum_sector_size)
        valuation_ranks.append(rank_name)
    output["cheap__fcf_yield"] = _sector_percentile(
        output, "fcf_yield", True, config.minimum_sector_size
    )
    valuation_ranks.append("cheap__fcf_yield")
    output["cheapness_score"] = output[valuation_ranks].mean(axis=1) * 100.0

    history_ranks = []
    for column in (
        "pe_vs_history",
        "pfcf_vs_history",
        "ps_vs_history",
        "pb_vs_history",
        "ev_to_ebitda_vs_history",
    ):
        rank_name = f"discount__{column}"
        output[rank_name] = _global_percentile(output[column], higher_better=False)
        history_ranks.append(rank_name)
    output["own_history_discount_score"] = output[history_ranks].mean(axis=1) * 100.0

    quality_specs = {
        "roic": True,
        "operating_margin": True,
        "fcf_margin": True,
        "piotroski": True,
        "altman_z": True,
        "net_debt_to_operating_income": False,
        "income_quality": True,
    }
    quality_ranks = []
    for column, higher_better in quality_specs.items():
        rank_name = f"quality__{column}"
        output[rank_name] = _sector_percentile(
            output, column, higher_better, config.minimum_sector_size
        )
        quality_ranks.append(rank_name)
    output["quality_score"] = output[quality_ranks].mean(axis=1) * 100.0

    expectation_specs = {
        "revenue_growth": True,
        "eps_growth": True,
        "eps_revision": True,
        "revenue_revision": True,
        "target_revision": True,
        "target_upside": True,
        "recommendation_score": True,
        "fmp_rating_score": True,
    }
    expectation_ranks = []
    for column, higher_better in expectation_specs.items():
        rank_name = f"expectation__{column}"
        output[rank_name] = _sector_percentile(
            output, column, higher_better, config.minimum_sector_size
        )
        expectation_ranks.append(rank_name)
    output["expectation_support_score"] = output[expectation_ranks].mean(axis=1) * 100.0

    sufficient_price_history = output["price_history_days"] >= 10
    output["price_trough_score"] = (
        _sector_percentile(output, "price_drawdown", False, config.minimum_sector_size) * 100.0
    ).where(sufficient_price_history)
    price_heat_parts = pd.concat(
        [
            _sector_percentile(output, "price_drawdown", True, config.minimum_sector_size),
            _sector_percentile(output, "price_return_10d", True, config.minimum_sector_size),
        ],
        axis=1,
    )
    output["price_heat_score"] = (price_heat_parts.mean(axis=1) * 100.0).where(
        sufficient_price_history
    )

    output["expensiveness_score"] = 100.0 - output["cheapness_score"]
    output["own_history_premium_score"] = 100.0 - output["own_history_discount_score"]
    output["weak_quality_score"] = 100.0 - output["quality_score"]
    output["expectation_fragility_score"] = 100.0 - output["expectation_support_score"]
    output["value_trough_score"] = _weighted_score(output, VALUE_COMPONENT_WEIGHTS)
    output["overvaluation_score"] = _weighted_score(
        output, OVERVALUATION_COMPONENT_WEIGHTS
    )

    value_trap = (output["net_income"] <= 0) & (output["free_cash_flow"] <= 0)
    weak_balance = (output["piotroski"] < 4) | (
        output["net_debt_to_operating_income"] > 5
    )
    output.loc[value_trap, "value_trough_score"] *= 0.65
    output.loc[weak_balance.fillna(False), "value_trough_score"] *= 0.82
    output.loc[value_trap, "overvaluation_score"] = (
        output.loc[value_trap, "overvaluation_score"] + 8.0
    ).clip(upper=100.0)
    output["value_trap_flag"] = value_trap
    output["weak_balance_flag"] = weak_balance.fillna(False)
    output["value_reason"] = output.apply(_value_reason, axis=1)
    output["overvaluation_reason"] = output.apply(_overvaluation_reason, axis=1)
    return output


def _value_reason(row: pd.Series) -> str:
    components = {
        "同行估值较低": row.get("cheapness_score"),
        "低于自身历史估值": row.get("own_history_discount_score"),
        "财务质量支撑": row.get("quality_score"),
        "预期仍有支撑": row.get("expectation_support_score"),
        "价格处于短期低位": row.get("price_trough_score"),
    }
    reasons = _top_components(components)
    if row.get("value_trap_flag"):
        reasons.append("警惕盈利与现金流同时为负")
    if row.get("weak_balance_flag"):
        reasons.append("警惕资产负债表")
    return "；".join(reasons[:4])


def _overvaluation_reason(row: pd.Series) -> str:
    components = {
        "同行估值偏高": row.get("expensiveness_score"),
        "高于自身历史估值": row.get("own_history_premium_score"),
        "财务质量支撑偏弱": row.get("weak_quality_score"),
        "预期支撑偏弱": row.get("expectation_fragility_score"),
        "价格短期过热": row.get("price_heat_score"),
    }
    reasons = _top_components(components)
    if row.get("value_trap_flag"):
        reasons.append("盈利与现金流同时为负")
    return "；".join(reasons[:4])


def select_watchlists(
    radar: pd.DataFrame,
    config: ValuationRadarConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    eligible = radar.loc[radar["eligible"]].copy()
    value_candidates = eligible.loc[
        (eligible["cheapness_score"] >= config.minimum_value_cheapness_score)
        & (eligible["quality_score"] >= config.minimum_value_quality_score)
        & (
            eligible["expectation_support_score"]
            >= config.minimum_value_expectation_score
        )
        & ~eligible["value_trap_flag"]
        & ~eligible["weak_balance_flag"]
    ]
    value = value_candidates.sort_values(
        ["value_trough_score", "data_coverage", "market_cap"], ascending=[False, False, False]
    ).head(config.watchlist_size)
    value_symbols = set(value["security_id"])
    overvaluation_candidates = eligible.loc[
        (
            eligible["expensiveness_score"]
            >= config.minimum_overvaluation_expensiveness_score
        )
        | (
            eligible["own_history_premium_score"]
            >= config.minimum_overvaluation_history_premium_score
        )
    ]
    overvalued = overvaluation_candidates.loc[
        ~overvaluation_candidates["security_id"].isin(value_symbols)
    ].sort_values(
        ["overvaluation_score", "data_coverage", "market_cap"], ascending=[False, False, False]
    ).head(config.watchlist_size)
    value = value.copy()
    overvalued = overvalued.copy()
    value["watchlist"] = "value_trough"
    overvalued["watchlist"] = "overvaluation_risk"
    value["watch_rank"] = range(1, len(value) + 1)
    overvalued["watch_rank"] = range(1, len(overvalued) + 1)
    return value, overvalued


def evaluate_matured_history(
    history_dir: Path,
    bars: pd.DataFrame,
    config: ValuationRadarConfig,
) -> dict[str, Any]:
    files = sorted(history_dir.glob("valuation_scores_*.csv")) if history_dir.exists() else []
    if not files:
        return _empty_forward_evaluation(config)
    snapshots = pd.concat([pd.read_csv(path) for path in files], ignore_index=True)
    snapshots["signal_date"] = pd.to_datetime(snapshots["signal_date"]).dt.date
    snapshots["as_of_utc"] = pd.to_datetime(snapshots["as_of_utc"], utc=True)
    snapshots = snapshots.sort_values("as_of_utc").drop_duplicates(
        ["signal_date", "security_id"], keep="last"
    )
    bars = _dedupe_bars(bars)
    dates = sorted(bars["trade_date"].unique())
    date_index = {item: index for index, item in enumerate(dates)}
    evaluations: dict[str, Any] = {}
    for horizon in config.forward_horizons:
        matured = 0
        value_excess: list[float] = []
        over_excess: list[float] = []
        for signal_date, group in snapshots.groupby("signal_date"):
            index = date_index.get(signal_date)
            if index is None or index + horizon >= len(dates):
                continue
            future_date = dates[index + horizon]
            start = bars.loc[bars["trade_date"] == signal_date, ["security_id", "close"]].rename(
                columns={"close": "start_close"}
            )
            end = bars.loc[bars["trade_date"] == future_date, ["security_id", "close"]].rename(
                columns={"close": "end_close"}
            )
            returns = start.merge(end, on="security_id")
            returns["forward_return"] = returns["end_close"] / returns["start_close"] - 1.0
            scored = group.merge(returns[["security_id", "forward_return"]], on="security_id")
            if scored.empty:
                continue
            benchmark = float(scored["forward_return"].mean())
            group_for_selection = group.copy()
            group_for_selection["eligible"] = True
            group_for_selection["expensiveness_score"] = (
                100.0 - group_for_selection["cheapness_score"]
            )
            group_for_selection["own_history_premium_score"] = (
                100.0 - group_for_selection["own_history_discount_score"]
            )
            value_top, over_top = select_watchlists(group_for_selection, config)
            value_returns = value_top[["security_id"]].merge(
                returns[["security_id", "forward_return"]], on="security_id"
            )
            over_returns = over_top[["security_id"]].merge(
                returns[["security_id", "forward_return"]], on="security_id"
            )
            if not value_returns.empty:
                value_excess.append(
                    float(value_returns["forward_return"].mean() - benchmark)
                )
            if not over_returns.empty:
                over_excess.append(
                    float(over_returns["forward_return"].mean() - benchmark)
                )
            matured += 1
        evaluations[str(horizon)] = {
            "matured_signal_dates": matured,
            "average_value_trough_excess_return": _mean_or_none(value_excess),
            "average_overvaluation_excess_return": _mean_or_none(over_excess),
            "average_overvaluation_avoidance_alpha": (
                -_mean_or_none(over_excess) if over_excess else None
            ),
            "status": "available" if matured >= 20 else "insufficient_matured_signals",
        }
    return {"horizons": evaluations}


def _empty_forward_evaluation(config: ValuationRadarConfig) -> dict[str, Any]:
    return {
        "horizons": {
            str(horizon): {
                "matured_signal_dates": 0,
                "average_value_trough_excess_return": None,
                "average_overvaluation_excess_return": None,
                "average_overvaluation_avoidance_alpha": None,
                "status": "insufficient_matured_signals",
            }
            for horizon in config.forward_horizons
        }
    }


def write_valuation_outputs(
    output_dir: Path,
    radar: pd.DataFrame,
    value_watchlist: pd.DataFrame,
    overvaluation_watchlist: pd.DataFrame,
    audit: dict[str, Any],
    forward_evaluation: dict[str, Any],
    config: ValuationRadarConfig,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    history_dir = output_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    signal_date = radar["signal_date"].max().isoformat()
    timestamp = pd.Timestamp(radar["as_of_utc"].max()).strftime("%Y%m%dT%H%M%SZ")
    all_path = output_dir / f"valuation_radar_{signal_date}.csv"
    value_path = output_dir / f"value_trough_watchlist_{signal_date}.csv"
    over_path = output_dir / f"overvaluation_watchlist_{signal_date}.csv"
    report_path = output_dir / f"valuation_radar_report_{signal_date}.json"
    history_path = history_dir / f"valuation_scores_{signal_date}_{timestamp}.csv"

    columns = _output_columns()
    radar.loc[radar["eligible"], columns].sort_values(
        "value_trough_score", ascending=False
    ).to_csv(all_path, index=False)
    value_watchlist[columns + ["watchlist", "watch_rank"]].to_csv(value_path, index=False)
    overvaluation_watchlist[columns + ["watchlist", "watch_rank"]].to_csv(
        over_path, index=False
    )
    radar.loc[radar["eligible"], columns].to_csv(history_path, index=False)
    report = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "signal_date": signal_date,
        "as_of_utc": pd.Timestamp(radar["as_of_utc"].max()).isoformat(),
        "config": asdict(config),
        "score_definition": {
            "value_trough": VALUE_COMPONENT_WEIGHTS,
            "overvaluation_risk": OVERVALUATION_COMPONENT_WEIGHTS,
        },
        "audit": audit,
        "forward_evaluation": forward_evaluation,
        "deployment_status": "observation_only",
        "model_status": "rule_based_pit_composite_waiting_for_matured_labels",
        "warning": (
            "The PIT history does not yet contain matured 20/60-session labels. "
            "These are observation watchlists, not buy/sell portfolios."
        ),
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "radar": all_path,
        "value_watchlist": value_path,
        "overvaluation_watchlist": over_path,
        "report": report_path,
        "history_snapshot": history_path,
    }


def _output_columns() -> list[str]:
    return [
        "security_id",
        "symbol",
        "company_name",
        "sector",
        "industry",
        "signal_date",
        "as_of_utc",
        "close",
        "market_cap",
        "dollar_volume",
        "value_trough_score",
        "overvaluation_score",
        "cheapness_score",
        "expensiveness_score",
        "own_history_discount_score",
        "own_history_premium_score",
        "quality_score",
        "weak_quality_score",
        "expectation_support_score",
        "expectation_fragility_score",
        "price_trough_score",
        "price_heat_score",
        "data_coverage",
        "pe",
        "pfcf",
        "ps",
        "pb",
        "ev_to_operating_income",
        "ev_to_ebitda",
        "fcf_yield",
        "roic",
        "operating_margin",
        "fcf_margin",
        "piotroski",
        "altman_z",
        "revenue_growth",
        "eps_growth",
        "eps_revision",
        "revenue_revision",
        "target_upside",
        "target_revision",
        "price_history_days",
        "price_drawdown",
        "price_return_10d",
        "valuation_anchor_period_end",
        "valuation_anchor_market_cap",
        "value_trap_flag",
        "weak_balance_flag",
        "value_reason",
        "overvaluation_reason",
    ]


def _audit_payload(
    radar: pd.DataFrame,
    frames: dict[str, pd.DataFrame],
    as_of: datetime,
    config: ValuationRadarConfig,
) -> dict[str, Any]:
    violations = 0
    for frame in frames.values():
        if "fetched_at" in frame:
            violations += int((frame["fetched_at"] > pd.Timestamp(as_of)).sum())
    eligible = radar.loc[radar["eligible"]]
    return {
        "as_of_utc": as_of.isoformat(),
        "signal_date": radar["signal_date"].max().isoformat(),
        "total_price_symbols": int(radar["security_id"].nunique()),
        "eligible_symbols": int(eligible["security_id"].nunique()),
        "median_data_coverage": float(eligible["data_coverage"].median()) if not eligible.empty else 0,
        "feature_asof_violations": violations,
        "price_history_days_median": float(eligible["price_history_days"].median()) if not eligible.empty else 0,
        "price_history_warning": "Price history is too short for a 52-week-low feature.",
        "valuation_method": (
            "Latest disclosed FMP valuation ratios re-anchored by the PIT current "
            "market-cap ratio; cumulative quarterly statements are not summed."
        ),
        "forward_horizons": list(config.forward_horizons),
    }
