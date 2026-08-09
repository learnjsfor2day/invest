from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy.engine import Engine

from pit_radar import scoring, valuation_radar as valuation
from pit_radar.scoring import (
    as_bool as _as_bool,
    ensure_utc as _ensure_utc,
    finite_float as _finite_float,
    is_finite as _finite,
    is_positive as _positive,
    positive_ratio as _positive_ratio,
    ratio as _ratio,
    scaled_change as _scaled_change,
)


@dataclass(frozen=True)
class InflectionRadarConfig:
    watchlist_size: int = 20
    minimum_price: float = 3.0
    minimum_market_cap: float = 300_000_000.0
    minimum_dollar_volume: float = 5_000_000.0
    minimum_data_coverage: float = 0.30
    minimum_sector_size: int = 12
    forward_horizons: tuple[int, ...] = (20, 60, 120)


COMPONENT_WEIGHTS = {
    "revision_score": 0.30,
    "fundamental_score": 0.25,
    "confirmation_score": 0.20,
    "valuation_score": 0.15,
    "catalyst_score": 0.10,
}

COMPONENT_LABELS = {
    "revision_score": "盈利预期上修",
    "fundamental_score": "基本面加速",
    "confirmation_score": "价格与成交确认",
    "valuation_score": "估值仍有空间",
    "catalyst_score": "行业与评级催化",
}

FEATURE_COLUMNS = (
    "q_eps_revision_20d",
    "q_revenue_revision_20d",
    "fy_eps_revision_20d",
    "target_revision_20d",
    "revenue_growth",
    "eps_growth",
    "free_cash_flow_growth",
    "revenue_growth_acceleration",
    "eps_growth_acceleration",
    "operating_margin",
    "fcf_margin",
    "sector_relative_return_20d",
    "sector_relative_return_60d",
    "price_return_120d",
    "volume_ratio_20d",
    "forward_pe",
    "target_upside",
    "recommendation_score",
    "sector_revision_breadth",
)


def build_inflection_radar(
    engine: Engine,
    as_of: datetime,
    config: InflectionRadarConfig | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    config = config or InflectionRadarConfig()
    as_of = _ensure_utc(as_of)
    frames = valuation._load_frames(engine, as_of)
    base_config = valuation.ValuationRadarConfig(
        minimum_price=config.minimum_price,
        minimum_market_cap=config.minimum_market_cap,
        minimum_dollar_volume=config.minimum_dollar_volume,
        minimum_data_coverage=0.0,
        minimum_sector_size=config.minimum_sector_size,
    )
    radar = valuation._assemble_features(frames, as_of, base_config)
    radar = valuation._score_radar(radar, base_config)
    signal_date = radar["signal_date"].max()

    additions = (
        _extended_price_features(frames["bars"], signal_date),
        _estimate_revision_features(frames["estimates"], signal_date, as_of),
        _analyst_revision_features(frames["analysts"], as_of),
        _growth_acceleration_features(frames["growth"]),
    )
    for feature_frame in additions:
        radar = radar.merge(feature_frame, on="security_id", how="left")

    radar["sector"] = radar["sector"].fillna("Unknown")
    for window in (20, 60, 120):
        column = f"price_return_{window}d"
        radar[f"sector_relative_return_{window}d"] = radar[column] - radar.groupby(
            "sector"
        )[column].transform("median")

    radar["forward_pe"] = _positive_ratio(radar["close"], radar["next_fy_eps_mean"])
    positive_revision = radar["q_eps_revision_20d"].gt(0).where(
        radar["q_eps_revision_20d"].notna()
    )
    radar["sector_revision_breadth"] = positive_revision.groupby(radar["sector"]).transform(
        "mean"
    )
    radar["inflection_data_coverage"] = radar[list(FEATURE_COLUMNS)].notna().mean(axis=1)
    radar = _score_inflection_radar(radar, config)
    radar["universe_eligible"] = (
        (radar["close"] >= config.minimum_price)
        & (radar["market_cap"] >= config.minimum_market_cap)
        & (radar["dollar_volume"] >= config.minimum_dollar_volume)
        & (radar["inflection_data_coverage"] >= config.minimum_data_coverage)
    )
    radar["core_signal_ready"] = radar["revision_score"].notna() & radar[
        "fundamental_score"
    ].notna()
    radar["eligible"] = radar["universe_eligible"] & radar["core_signal_ready"]

    audit = {
        "as_of_utc": as_of.isoformat(),
        "signal_date": signal_date.isoformat(),
        "total_price_symbols": int(len(radar)),
        "universe_eligible_symbols": int(radar["universe_eligible"].sum()),
        "core_signal_ready_symbols": int(radar["core_signal_ready"].sum()),
        "eligible_symbols": int(radar["eligible"].sum()),
        "median_data_coverage": _finite_float(radar["inflection_data_coverage"].median()),
        "price_history_days_median": _finite_float(radar["price_history_days"].median()),
        "symbols_with_20d_price_history": int(radar["price_return_20d"].notna().sum()),
        "symbols_with_60d_price_history": int(radar["price_return_60d"].notna().sum()),
        "symbols_with_confirmation_score": int(radar["confirmation_score"].notna().sum()),
        "symbols_with_20d_estimate_revision": int(radar["q_eps_revision_20d"].notna().sum()),
        "deployment_status": "observation_only",
    }
    return radar, audit


def select_inflection_watchlist(
    radar: pd.DataFrame,
    config: InflectionRadarConfig | None = None,
) -> pd.DataFrame:
    config = config or InflectionRadarConfig()
    selected = radar.loc[radar["eligible"]].sort_values(
        ["inflection_score", "inflection_data_coverage", "dollar_volume"],
        ascending=[False, False, False],
    ).head(config.watchlist_size).copy()
    selected["watch_rank"] = range(1, len(selected) + 1)
    return selected


def _extended_price_features(bars: pd.DataFrame, signal_date: date) -> pd.DataFrame:
    history = valuation._dedupe_bars(bars)
    history = history.loc[history["trade_date"] <= signal_date].copy()
    history = history.sort_values(["security_id", "trade_date"])
    groups = history.groupby("security_id", sort=False)
    history["daily_return"] = groups["close"].pct_change(fill_method=None)
    history["price_history_days_extended"] = groups["close"].transform("count")
    for window in (20, 60, 120):
        history[f"price_return_{window}d"] = groups["close"].pct_change(
            window, fill_method=None
        )
    history["volume_median_20d"] = groups["volume"].transform(
        lambda values: values.rolling(20, min_periods=10).median()
    )
    history["volume_ratio_20d"] = _ratio(
        history["volume"], history["volume_median_20d"]
    )
    history["volatility_20d"] = history.groupby("security_id")["daily_return"].transform(
        lambda values: values.rolling(20, min_periods=10).std()
    )
    history["high_252d"] = groups["close"].transform(
        lambda values: values.rolling(252, min_periods=126).max()
    )
    history["distance_from_52w_high"] = _ratio(history["close"], history["high_252d"]) - 1.0
    columns = [
        "security_id",
        "price_history_days_extended",
        "price_return_20d",
        "price_return_60d",
        "price_return_120d",
        "volume_ratio_20d",
        "volatility_20d",
        "distance_from_52w_high",
    ]
    return history.loc[history["trade_date"] == signal_date, columns].drop_duplicates(
        "security_id", keep="last"
    )


def _estimate_revision_features(
    estimates: pd.DataFrame,
    signal_date: date,
    as_of: datetime,
) -> pd.DataFrame:
    outputs = []
    for period_type, prefix in (("quarter", "q"), ("fiscal_year", "fy")):
        part = estimates.loc[
            (estimates["period_type"] == period_type)
            & (estimates["fiscal_period_end"] >= signal_date)
        ].copy()
        if part.empty:
            continue
        chosen = part.groupby("security_id")["fiscal_period_end"].min().rename(
            "selected_period"
        )
        part = part.merge(chosen, on="security_id")
        part = part.loc[part["fiscal_period_end"] == part["selected_period"]]
        part = part.sort_values(
            ["security_id", "fetched_at", "recorded_at", "estimate_id"]
        )
        current = part.drop_duplicates("security_id", keep="last").copy()
        result = current[
            ["security_id", "fiscal_period_end", "eps_mean", "revenue_mean"]
        ].rename(
            columns={
                "fiscal_period_end": f"next_{prefix}_period_end",
                "eps_mean": f"next_{prefix}_eps_mean",
                "revenue_mean": f"next_{prefix}_revenue_mean",
            }
        )
        for days in (20, 60):
            prior = part.loc[
                part["fetched_at"] <= pd.Timestamp(as_of - timedelta(days=days))
            ].drop_duplicates("security_id", keep="last")
            prior = prior[["security_id", "eps_mean", "revenue_mean"]].rename(
                columns={
                    "eps_mean": f"prior_eps_{days}d",
                    "revenue_mean": f"prior_revenue_{days}d",
                }
            )
            result = result.merge(prior, on="security_id", how="left")
            result[f"{prefix}_eps_revision_{days}d"] = _scaled_change(
                result[f"next_{prefix}_eps_mean"], result[f"prior_eps_{days}d"], 0.10
            )
            result[f"{prefix}_revenue_revision_{days}d"] = _scaled_change(
                result[f"next_{prefix}_revenue_mean"],
                result[f"prior_revenue_{days}d"],
                1.0,
            )
            result = result.drop(columns=[f"prior_eps_{days}d", f"prior_revenue_{days}d"])
        outputs.append(result)
    if not outputs:
        return pd.DataFrame(columns=["security_id"])
    merged = outputs[0]
    for output in outputs[1:]:
        merged = merged.merge(output, on="security_id", how="outer")
    return merged


def _analyst_revision_features(analysts: pd.DataFrame, as_of: datetime) -> pd.DataFrame:
    if analysts.empty:
        return pd.DataFrame(columns=["security_id", "target_revision_20d", "target_revision_60d"])
    part = analysts.sort_values(
        ["security_id", "fetched_at", "recorded_at", "analyst_snapshot_id"]
    )
    current = part.drop_duplicates("security_id", keep="last")[
        ["security_id", "target_mean"]
    ].rename(columns={"target_mean": "current_target_mean"})
    result = current
    for days in (20, 60):
        prior = part.loc[
            part["fetched_at"] <= pd.Timestamp(as_of - timedelta(days=days))
        ].drop_duplicates("security_id", keep="last")
        prior = prior[["security_id", "target_mean"]].rename(
            columns={"target_mean": f"prior_target_{days}d"}
        )
        result = result.merge(prior, on="security_id", how="left")
        result[f"target_revision_{days}d"] = _scaled_change(
            result["current_target_mean"], result[f"prior_target_{days}d"], 0.10
        )
        result = result.drop(columns=f"prior_target_{days}d")
    return result.drop(columns="current_target_mean")


def _growth_acceleration_features(growth: pd.DataFrame) -> pd.DataFrame:
    if growth.empty:
        return pd.DataFrame(columns=["security_id"])
    part = valuation._dedupe_facts(growth)
    quarter = part.loc[part["period_type"] == "quarter"].copy()
    if quarter.empty:
        quarter = part.copy()
    quarter = quarter.sort_values(["security_id", "fiscal_period_end"])
    for column in ("revenue_growth", "eps_growth", "free_cash_flow_growth"):
        quarter[f"{column}_acceleration"] = quarter.groupby("security_id")[column].diff()
    latest = quarter.drop_duplicates("security_id", keep="last")
    return latest[
        [
            "security_id",
            "revenue_growth_acceleration",
            "eps_growth_acceleration",
            "free_cash_flow_growth_acceleration",
        ]
    ]


def _score_inflection_radar(
    frame: pd.DataFrame,
    config: InflectionRadarConfig,
) -> pd.DataFrame:
    output = frame.copy()
    specs = {
        "revision_score": {
            "q_eps_revision_20d": True,
            "q_revenue_revision_20d": True,
            "fy_eps_revision_20d": True,
            "target_revision_20d": True,
            "eps_revision": True,
        },
        "fundamental_score": {
            "revenue_growth": True,
            "eps_growth": True,
            "free_cash_flow_growth": True,
            "revenue_growth_acceleration": True,
            "eps_growth_acceleration": True,
            "operating_margin": True,
            "fcf_margin": True,
            "roic": True,
        },
        "confirmation_score": {
            "sector_relative_return_20d": True,
            "sector_relative_return_60d": True,
            "price_return_120d": True,
            "volume_ratio_20d": True,
            "distance_from_52w_high": True,
        },
        "valuation_score": {
            "cheapness_score": True,
            "own_history_discount_score": True,
            "forward_pe": False,
            "target_upside": True,
        },
        "catalyst_score": {
            "recommendation_score": True,
            "fmp_rating_score": True,
            "sector_revision_breadth": True,
        },
    }
    minimum_component_features = {
        "revision_score": 2,
        "fundamental_score": 3,
        "confirmation_score": 2,
        "valuation_score": 2,
        "catalyst_score": 1,
    }
    for component, feature_specs in specs.items():
        ranked = []
        for column, higher_better in feature_specs.items():
            rank_column = f"rank__{component}__{column}"
            if column in {"cheapness_score", "own_history_discount_score"}:
                output[rank_column] = pd.to_numeric(output[column], errors="coerce") / 100.0
            else:
                output[rank_column] = scoring.sector_percentile(
                    output, column, higher_better, config.minimum_sector_size
                )
            ranked.append(rank_column)
        ranked_frame = output[ranked]
        output[component] = (ranked_frame.mean(axis=1) * 100.0).where(
            ranked_frame.notna().sum(axis=1) >= minimum_component_features[component]
        )

    output["raw_inflection_score"] = scoring.weighted_score(output, COMPONENT_WEIGHTS)
    volatility_risk = scoring.sector_percentile(
        output, "volatility_20d", True, config.minimum_sector_size
    )
    balance_risk = scoring.sector_percentile(
        output, "net_debt_to_operating_income", True, config.minimum_sector_size
    )
    risk_parts = pd.concat([volatility_risk, balance_risk], axis=1).mean(axis=1)
    output["risk_penalty"] = (risk_parts * 15.0).fillna(0.0)
    output.loc[output["value_trap_flag"].fillna(False), "risk_penalty"] += 10.0
    output.loc[output["weak_balance_flag"].fillna(False), "risk_penalty"] += 5.0
    output["risk_penalty"] = output["risk_penalty"].clip(0.0, 30.0)
    output["inflection_score"] = (
        output["raw_inflection_score"] - output["risk_penalty"]
    ).clip(0.0, 100.0)
    output["inflection_reason"] = output.apply(_inflection_reason, axis=1)
    return output


def _inflection_reason(row: pd.Series) -> str:
    reasons: list[str] = []
    if _positive(row.get("q_eps_revision_20d")):
        reasons.append("下季EPS预期20日上修")
    if _positive(row.get("q_revenue_revision_20d")):
        reasons.append("下季营收预期20日上修")
    if _positive(row.get("revenue_growth_acceleration")):
        reasons.append("收入增长加速")
    if _positive(row.get("sector_relative_return_20d")):
        reasons.append("20日跑赢行业")
    if _finite(row.get("target_upside")) and float(row["target_upside"]) >= 0.20:
        reasons.append("目标价空间较大")
    if _finite(row.get("sector_revision_breadth")) and float(row["sector_revision_breadth"]) >= 0.60:
        reasons.append("行业预期上修扩散")
    if not reasons:
        component_values = {
            COMPONENT_LABELS[column]: row.get(column) for column in COMPONENT_WEIGHTS
        }
        reasons = [
            name
            for name, value in sorted(
                component_values.items(),
                key=lambda item: float(item[1]) if _finite(item[1]) else -1.0,
                reverse=True,
            )[:3]
        ]
    return "、".join(reasons[:4])


def evaluate_forward_labels(
    history_dir: Path,
    bars: pd.DataFrame,
    config: InflectionRadarConfig | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    config = config or InflectionRadarConfig()
    snapshots = _load_latest_history_snapshots(history_dir)
    if not snapshots:
        return _empty_labels(), _empty_evaluation(config)
    clean_bars = valuation._dedupe_bars(bars)
    if clean_bars.empty:
        return _empty_labels(), _empty_evaluation(config)
    trading_dates = sorted(clean_bars["trade_date"].drop_duplicates().tolist())
    date_index = {value: index for index, value in enumerate(trading_dates)}
    price_lookup = clean_bars[["security_id", "trade_date", "close"]]
    labels: list[pd.DataFrame] = []
    summaries: dict[str, dict[str, Any]] = {}

    for horizon in config.forward_horizons:
        matured_dates = 0
        horizon_labels: list[pd.DataFrame] = []
        for signal_date, snapshot in snapshots.items():
            if signal_date not in date_index:
                continue
            end_index = date_index[signal_date] + horizon
            if end_index >= len(trading_dates):
                continue
            end_date = trading_dates[end_index]
            start_prices = price_lookup.loc[price_lookup["trade_date"] == signal_date, ["security_id", "close"]].rename(
                columns={"close": "start_close"}
            )
            end_prices = price_lookup.loc[price_lookup["trade_date"] == end_date, ["security_id", "close"]].rename(
                columns={"close": "end_close"}
            )
            scored = snapshot.merge(start_prices, on="security_id").merge(end_prices, on="security_id")
            if scored.empty:
                continue
            scored["forward_return"] = _ratio(scored["end_close"], scored["start_close"]) - 1.0
            market_median = scored["forward_return"].median()
            sector_median = scored.groupby("sector")["forward_return"].transform("median")
            sector_count = scored.groupby("sector")["forward_return"].transform("count")
            scored["benchmark_return"] = sector_median.where(
                sector_count >= config.minimum_sector_size, market_median
            )
            scored["forward_excess_return"] = scored["forward_return"] - scored["benchmark_return"]
            scored["horizon"] = horizon
            scored["label_end_date"] = end_date
            scored["signal_date"] = signal_date
            horizon_labels.append(scored)
            matured_dates += 1
        if horizon_labels:
            combined = pd.concat(horizon_labels, ignore_index=True)
            labels.append(combined)
            daily_top = []
            for _, group in combined.groupby("signal_date"):
                eligible = group.loc[_as_bool(group["eligible"])].sort_values(
                    "inflection_score", ascending=False
                ).head(config.watchlist_size)
                if not eligible.empty:
                    daily_top.append(
                        {
                            "mean_return": eligible["forward_return"].mean(),
                            "mean_excess": eligible["forward_excess_return"].mean(),
                            "hit_rate": eligible["forward_excess_return"].gt(0).mean(),
                        }
                    )
            top_frame = pd.DataFrame(daily_top)
            summaries[str(horizon)] = {
                "matured_signal_dates": matured_dates,
                "average_watchlist_return": _finite_float(top_frame["mean_return"].mean()) if not top_frame.empty else None,
                "average_watchlist_excess_return": _finite_float(top_frame["mean_excess"].mean()) if not top_frame.empty else None,
                "positive_excess_hit_rate": _finite_float(top_frame["hit_rate"].mean()) if not top_frame.empty else None,
                "status": "available",
            }
        else:
            summaries[str(horizon)] = {
                "matured_signal_dates": 0,
                "average_watchlist_return": None,
                "average_watchlist_excess_return": None,
                "positive_excess_hit_rate": None,
                "status": "insufficient_matured_signals",
            }
    label_frame = pd.concat(labels, ignore_index=True) if labels else _empty_labels()
    return label_frame, {"horizons": summaries}


def write_inflection_outputs(
    output_dir: Path,
    radar: pd.DataFrame,
    watchlist: pd.DataFrame,
    labels: pd.DataFrame,
    audit: dict[str, Any],
    evaluation: dict[str, Any],
    config: InflectionRadarConfig | None = None,
) -> dict[str, Path]:
    config = config or InflectionRadarConfig()
    output_dir.mkdir(parents=True, exist_ok=True)
    history_dir = output_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    signal_date = str(audit["signal_date"])
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    columns = [
        "security_id",
        "symbol",
        "company_name",
        "sector",
        "industry",
        "signal_date",
        "eligible",
        "inflection_score",
        "raw_inflection_score",
        "risk_penalty",
        "inflection_data_coverage",
        "revision_score",
        "fundamental_score",
        "confirmation_score",
        "valuation_score",
        "catalyst_score",
        "close",
        "market_cap",
        "dollar_volume",
        "q_eps_revision_20d",
        "q_revenue_revision_20d",
        "fy_eps_revision_20d",
        "revenue_growth",
        "eps_growth",
        "revenue_growth_acceleration",
        "sector_relative_return_20d",
        "sector_relative_return_60d",
        "price_return_120d",
        "forward_pe",
        "target_upside",
        "sector_revision_breadth",
        "inflection_reason",
    ]
    available_columns = [column for column in columns if column in radar]
    radar_path = output_dir / f"inflection_radar_{signal_date}.csv"
    watchlist_path = output_dir / f"inflection_watchlist_{signal_date}.csv"
    labels_path = output_dir / "inflection_forward_labels.csv"
    report_path = output_dir / f"inflection_report_{signal_date}.json"
    history_path = history_dir / f"inflection_scores_{signal_date}_{timestamp}.csv"
    radar.loc[radar["eligible"], available_columns].sort_values(
        "inflection_score", ascending=False
    ).to_csv(radar_path, index=False)
    watch_columns = ["watch_rank", *available_columns]
    watchlist[[column for column in watch_columns if column in watchlist]].to_csv(
        watchlist_path, index=False
    )
    radar.loc[radar["eligible"], available_columns].to_csv(history_path, index=False)
    labels.to_csv(labels_path, index=False)
    report = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "signal_date": signal_date,
        "config": asdict(config),
        "component_weights": COMPONENT_WEIGHTS,
        "audit": audit,
        "forward_evaluation": evaluation,
        "deployment_status": "observation_only",
        "warning": (
            "This is a transparent rule-based research ranking. It remains observation-only "
            "until multiple 20/60/120-session labels mature."
        ),
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "radar": radar_path,
        "watchlist": watchlist_path,
        "labels": labels_path,
        "report": report_path,
        "history_snapshot": history_path,
    }


def _load_latest_history_snapshots(history_dir: Path) -> dict[date, pd.DataFrame]:
    latest: dict[date, tuple[Path, pd.DataFrame]] = {}
    if not history_dir.exists():
        return {}
    for file_path in sorted(history_dir.glob("inflection_scores_*.csv")):
        frame = pd.read_csv(file_path)
        if frame.empty or "signal_date" not in frame:
            continue
        signal_date = pd.Timestamp(frame["signal_date"].iloc[0]).date()
        latest[signal_date] = (file_path, frame)
    return {signal_date: item[1] for signal_date, item in latest.items()}


def _empty_labels() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "signal_date",
            "label_end_date",
            "horizon",
            "security_id",
            "symbol",
            "forward_return",
            "benchmark_return",
            "forward_excess_return",
        ]
    )


def _empty_evaluation(config: InflectionRadarConfig) -> dict[str, Any]:
    return {
        "horizons": {
            str(horizon): {
                "matured_signal_dates": 0,
                "average_watchlist_return": None,
                "average_watchlist_excess_return": None,
                "positive_excess_hit_rate": None,
                "status": "insufficient_matured_signals",
            }
            for horizon in config.forward_horizons
        }
    }
