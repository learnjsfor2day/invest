from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pit_radar.scoring import ratio as _safe_ratio


NY_TZ = ZoneInfo("America/New_York")


FEATURE_LABELS = {
    "ret_1d": "近1日动量",
    "ret_3d": "近3日动量",
    "gap_return": "隔夜跳空",
    "intraday_return": "当日强弱",
    "range_pct": "日内振幅",
    "close_location": "收盘位置",
    "log_dollar_volume": "成交活跃度",
    "volume_ratio_3": "相对成交量",
    "volatility_3": "短期波动率",
    "target_upside": "分析师目标价空间",
    "recommendation_score": "分析师评级倾向",
    "next_q_eps_yield": "下季EPS价格比",
    "next_fy_eps_yield": "年度EPS价格比",
    "q_eps_dispersion": "EPS预期分歧",
    "q_revenue_dispersion": "营收预期分歧",
    "log_q_analyst_count": "预期覆盖人数",
    "days_to_next_q": "距离下季期末",
    "q_eps_revision": "EPS预期修正",
    "q_revenue_revision": "营收预期修正",
    "target_revision": "目标价修正",
}

MODEL_FEATURES = tuple(FEATURE_LABELS)


@dataclass(frozen=True)
class RadarConfig:
    top_k: int = 20
    minimum_train_dates: int = 4
    minimum_universe_size: int = 1000
    minimum_label_coverage: float = 0.90
    minimum_price: float = 3.0
    minimum_dollar_volume: float = 5_000_000.0
    transaction_cost_bps: float = 20.0
    ridge_alpha: float = 100.0
    cutoff_hour: int = 9
    cutoff_minute: int = 29


@dataclass(frozen=True)
class RidgeModel:
    intercept: float
    coefficients: dict[str, float]
    train_rows: int
    train_dates: int

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        output = np.full(len(frame), self.intercept, dtype=float)
        for feature, coefficient in self.coefficients.items():
            output += frame[f"z__{feature}"].to_numpy(dtype=float) * coefficient
        return output


def decision_cutoff(entry_date: date, config: RadarConfig) -> datetime:
    local = datetime.combine(
        entry_date,
        time(config.cutoff_hour, config.cutoff_minute),
        tzinfo=NY_TZ,
    )
    return local.astimezone(UTC)


def next_weekday(value: date) -> date:
    candidate = value + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def load_pit_frames(engine: Engine) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    bars = pd.read_sql_query(
        text(
            """
            SELECT
                d.daily_bar_id,
                d.security_id,
                s.primary_ticker AS symbol,
                s.company_name,
                s.sector,
                s.industry,
                d.trade_date,
                CAST(d.open AS REAL) AS open,
                CAST(d.high AS REAL) AS high,
                CAST(d.low AS REAL) AS low,
                CAST(d.close AS REAL) AS close,
                CAST(d.volume AS REAL) AS volume,
                d.fetched_at,
                d.recorded_at
            FROM pit.daily_market_bar d
            JOIN core.security s ON s.security_id = d.security_id
            WHERE d.close IS NOT NULL
            """
        ),
        engine,
    )
    estimates = pd.read_sql_query(
        text(
            """
            SELECT
                estimate_id,
                security_id,
                fiscal_period_end,
                period_type,
                CAST(eps_mean AS REAL) AS eps_mean,
                CAST(eps_high AS REAL) AS eps_high,
                CAST(eps_low AS REAL) AS eps_low,
                analyst_count_eps,
                CAST(revenue_mean AS REAL) AS revenue_mean,
                CAST(revenue_high AS REAL) AS revenue_high,
                CAST(revenue_low AS REAL) AS revenue_low,
                analyst_count_revenue,
                fetched_at,
                recorded_at
            FROM pit.estimate_snapshot
            """
        ),
        engine,
    )
    analysts = pd.read_sql_query(
        text(
            """
            SELECT
                analyst_snapshot_id,
                security_id,
                CAST(target_mean AS REAL) AS target_mean,
                CAST(target_high AS REAL) AS target_high,
                CAST(target_low AS REAL) AS target_low,
                strong_buy_count,
                buy_count,
                hold_count,
                sell_count,
                strong_sell_count,
                fetched_at,
                recorded_at
            FROM pit.analyst_snapshot
            """
        ),
        engine,
    )

    bars["trade_date"] = pd.to_datetime(bars["trade_date"]).dt.date
    estimates["fiscal_period_end"] = pd.to_datetime(estimates["fiscal_period_end"]).dt.date
    for frame in (bars, estimates, analysts):
        frame["fetched_at"] = pd.to_datetime(frame["fetched_at"], utc=True)
        frame["recorded_at"] = pd.to_datetime(frame["recorded_at"], utc=True)
    return bars, estimates, analysts


def build_radar_dataset(
    bars: pd.DataFrame,
    estimates: pd.DataFrame,
    analysts: pd.DataFrame,
    config: RadarConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    date_counts = bars.groupby("trade_date")["security_id"].nunique().sort_index()
    signal_dates = [
        item for item, count in date_counts.items() if int(count) >= config.minimum_universe_size
    ]
    if len(signal_dates) < 3:
        raise ValueError("Not enough broad-universe daily bars to build a radar dataset.")

    outputs: list[pd.DataFrame] = []
    audits: list[dict[str, Any]] = []
    for index, signal_date in enumerate(signal_dates):
        has_observed_entry = index + 1 < len(signal_dates)
        entry_date = signal_dates[index + 1] if has_observed_entry else next_weekday(signal_date)
        cutoff = decision_cutoff(entry_date, config)
        feature_frame = _build_signal_features(
            bars,
            estimates,
            analysts,
            signal_date,
            entry_date,
            cutoff,
            config,
        )

        if has_observed_entry:
            labels = _first_observed_labels(bars, entry_date)
            feature_frame = feature_frame.merge(labels, on="security_id", how="left")
        else:
            feature_frame["label_return"] = np.nan
            feature_frame["label_fetched_at"] = pd.NaT

        eligible = feature_frame["eligible"]
        eligible_count = int(eligible.sum())
        labeled_count = int((eligible & feature_frame["label_return"].notna()).sum())
        coverage = labeled_count / eligible_count if eligible_count else 0.0
        usable = bool(has_observed_entry and coverage >= config.minimum_label_coverage)
        feature_frame["label_date_usable"] = usable
        feature_frame["label_coverage"] = coverage
        outputs.append(feature_frame)
        audits.append(
            {
                "signal_date": signal_date.isoformat(),
                "entry_date": entry_date.isoformat(),
                "cutoff_utc": cutoff.isoformat(),
                "eligible_symbols": eligible_count,
                "labeled_symbols": labeled_count,
                "label_coverage": coverage,
                "label_date_usable": usable,
                "feature_asof_violations": int(feature_frame["asof_violation"].sum()),
            }
        )

    dataset = pd.concat(outputs, ignore_index=True)
    dataset = _add_revision_features(dataset)
    dataset = _add_cross_sectional_features(dataset)
    if bool(dataset["asof_violation"].any()):
        raise AssertionError("Feature dataset contains rows fetched after their decision cutoff.")
    return dataset, pd.DataFrame(audits)


def _build_signal_features(
    bars: pd.DataFrame,
    estimates: pd.DataFrame,
    analysts: pd.DataFrame,
    signal_date: date,
    entry_date: date,
    cutoff: datetime,
    config: RadarConfig,
) -> pd.DataFrame:
    cutoff_ts = pd.Timestamp(cutoff)
    history = bars.loc[
        (bars["trade_date"] <= signal_date) & (bars["fetched_at"] <= cutoff_ts)
    ].copy()
    history = (
        history.sort_values(
            ["security_id", "trade_date", "fetched_at", "recorded_at", "daily_bar_id"]
        )
        .drop_duplicates(["security_id", "trade_date"], keep="last")
        .sort_values(["security_id", "trade_date"])
    )
    groups = history.groupby("security_id", sort=False)
    history["prev_close"] = groups["close"].shift(1)
    history["ret_1d"] = groups["close"].pct_change(1, fill_method=None)
    history["ret_3d"] = groups["close"].pct_change(3, fill_method=None)
    history["volume_median_3"] = groups["volume"].transform(
        lambda series: series.rolling(3, min_periods=2).median()
    )
    history["volatility_3"] = history.groupby("security_id", sort=False)["ret_1d"].transform(
        lambda series: series.rolling(3, min_periods=2).std()
    )
    current = history.loc[history["trade_date"] == signal_date].copy()
    current["gap_return"] = _safe_ratio(current["open"], current["prev_close"]) - 1.0
    current["intraday_return"] = _safe_ratio(current["close"], current["open"]) - 1.0
    current["range_pct"] = _safe_ratio(current["high"] - current["low"], current["prev_close"])
    current["close_location"] = _safe_ratio(
        current["close"] - current["low"], current["high"] - current["low"]
    ) - 0.5
    current["dollar_volume"] = current["close"] * current["volume"]
    current["log_dollar_volume"] = np.log1p(current["dollar_volume"].clip(lower=0))
    current["volume_ratio_3"] = _safe_ratio(current["volume"], current["volume_median_3"]) - 1.0

    estimate_features = _latest_estimate_features(estimates, signal_date, cutoff_ts)
    analyst_features = _latest_analyst_features(analysts, cutoff_ts)
    current = current.merge(estimate_features, on="security_id", how="left")
    current = current.merge(analyst_features, on="security_id", how="left")

    current["target_upside"] = _safe_ratio(current["target_mean"], current["close"]) - 1.0
    rating_total = (
        current[["strong_buy_count", "buy_count", "hold_count", "sell_count", "strong_sell_count"]]
        .fillna(0)
        .sum(axis=1)
    )
    rating_numerator = (
        2 * current["strong_buy_count"].fillna(0)
        + current["buy_count"].fillna(0)
        - current["sell_count"].fillna(0)
        - 2 * current["strong_sell_count"].fillna(0)
    )
    current["recommendation_score"] = rating_numerator.where(rating_total > 0) / rating_total.where(
        rating_total > 0
    )
    current["next_q_eps_yield"] = _safe_ratio(current["q_eps_mean"], current["close"])
    current["next_fy_eps_yield"] = _safe_ratio(current["fy_eps_mean"], current["close"])
    current["q_eps_dispersion"] = _safe_ratio(
        current["q_eps_high"] - current["q_eps_low"], current["q_eps_mean"].abs()
    )
    current["q_revenue_dispersion"] = _safe_ratio(
        current["q_revenue_high"] - current["q_revenue_low"], current["q_revenue_mean"].abs()
    )
    analyst_counts = current[["q_eps_analysts", "q_revenue_analysts"]].apply(
        pd.to_numeric, errors="coerce"
    )
    current["log_q_analyst_count"] = np.log1p(analyst_counts.max(axis=1).clip(lower=0))
    current["days_to_next_q"] = current["q_period_end"].map(
        lambda item: (item - signal_date).days if isinstance(item, date) else np.nan
    )
    current["signal_date"] = signal_date
    current["entry_date"] = entry_date
    current["decision_cutoff_utc"] = cutoff_ts
    current["eligible"] = (
        (current["close"] >= config.minimum_price)
        & (current["dollar_volume"] >= config.minimum_dollar_volume)
        & current["open"].notna()
        & current["volume"].gt(0)
    )

    source_times = ["fetched_at", "q_fetched_at", "fy_fetched_at", "analyst_fetched_at"]
    for column in source_times:
        if column not in current:
            current[column] = pd.NaT
    current["asof_violation"] = False
    for column in source_times:
        current["asof_violation"] |= current[column].notna() & (current[column] > cutoff_ts)
    current["feature_coverage"] = current[list(MODEL_FEATURES[:-3])].notna().mean(axis=1)
    return current


def _latest_estimate_features(
    estimates: pd.DataFrame,
    signal_date: date,
    cutoff: pd.Timestamp,
) -> pd.DataFrame:
    visible = estimates.loc[
        (estimates["fetched_at"] <= cutoff)
        & (estimates["fiscal_period_end"] >= signal_date)
    ].copy()
    if visible.empty:
        return _empty_estimate_features()
    visible = (
        visible.sort_values(
            [
                "security_id",
                "period_type",
                "fiscal_period_end",
                "fetched_at",
                "recorded_at",
                "estimate_id",
            ]
        )
        .drop_duplicates(["security_id", "period_type", "fiscal_period_end"], keep="last")
        .sort_values(["security_id", "period_type", "fiscal_period_end"])
        .drop_duplicates(["security_id", "period_type"], keep="first")
    )
    output: pd.DataFrame | None = None
    source_columns = [
        "security_id",
        "fiscal_period_end",
        "eps_mean",
        "eps_high",
        "eps_low",
        "analyst_count_eps",
        "revenue_mean",
        "revenue_high",
        "revenue_low",
        "analyst_count_revenue",
        "fetched_at",
    ]
    for period_type, prefix in (("quarter", "q"), ("fiscal_year", "fy")):
        part = visible.loc[visible["period_type"] == period_type, source_columns].copy()
        part = part.rename(
            columns={
                "fiscal_period_end": f"{prefix}_period_end",
                "eps_mean": f"{prefix}_eps_mean",
                "eps_high": f"{prefix}_eps_high",
                "eps_low": f"{prefix}_eps_low",
                "analyst_count_eps": f"{prefix}_eps_analysts",
                "revenue_mean": f"{prefix}_revenue_mean",
                "revenue_high": f"{prefix}_revenue_high",
                "revenue_low": f"{prefix}_revenue_low",
                "analyst_count_revenue": f"{prefix}_revenue_analysts",
                "fetched_at": f"{prefix}_fetched_at",
            }
        )
        output = part if output is None else output.merge(part, on="security_id", how="outer")
    return output if output is not None else _empty_estimate_features()


def _empty_estimate_features() -> pd.DataFrame:
    columns = ["security_id"]
    for prefix in ("q", "fy"):
        columns.extend(
            [
                f"{prefix}_period_end",
                f"{prefix}_eps_mean",
                f"{prefix}_eps_high",
                f"{prefix}_eps_low",
                f"{prefix}_eps_analysts",
                f"{prefix}_revenue_mean",
                f"{prefix}_revenue_high",
                f"{prefix}_revenue_low",
                f"{prefix}_revenue_analysts",
                f"{prefix}_fetched_at",
            ]
        )
    return pd.DataFrame(columns=columns)


def _latest_analyst_features(analysts: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    visible = analysts.loc[analysts["fetched_at"] <= cutoff].copy()
    if visible.empty:
        return pd.DataFrame(
            columns=[
                "security_id",
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
        )
    return (
        visible.sort_values(
            ["security_id", "fetched_at", "recorded_at", "analyst_snapshot_id"]
        )
        .drop_duplicates("security_id", keep="last")
        .rename(columns={"fetched_at": "analyst_fetched_at"})
    )[
        [
            "security_id",
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
    ]


def _first_observed_labels(bars: pd.DataFrame, entry_date: date) -> pd.DataFrame:
    labels = bars.loc[bars["trade_date"] == entry_date].copy()
    if labels.empty:
        return pd.DataFrame(columns=["security_id", "label_return", "label_fetched_at"])
    labels = (
        labels.sort_values(["security_id", "fetched_at", "recorded_at", "daily_bar_id"])
        .drop_duplicates("security_id", keep="first")
    )
    labels["label_return"] = _safe_ratio(labels["close"], labels["open"]) - 1.0
    return labels.rename(columns={"fetched_at": "label_fetched_at"})[
        ["security_id", "label_return", "label_fetched_at"]
    ]


def _add_revision_features(dataset: pd.DataFrame) -> pd.DataFrame:
    dataset = dataset.sort_values(["security_id", "signal_date"]).copy()
    groups = dataset.groupby("security_id", sort=False)
    previous_q_period = groups["q_period_end"].shift(1)
    same_q_period = dataset["q_period_end"].eq(previous_q_period)
    previous_eps = groups["q_eps_mean"].shift(1)
    previous_revenue = groups["q_revenue_mean"].shift(1)
    previous_target = groups["target_mean"].shift(1)
    dataset["q_eps_revision"] = (
        _safe_ratio(dataset["q_eps_mean"], previous_eps) - 1.0
    ).where(same_q_period)
    dataset["q_revenue_revision"] = (
        _safe_ratio(dataset["q_revenue_mean"], previous_revenue) - 1.0
    ).where(same_q_period)
    dataset["target_revision"] = _safe_ratio(dataset["target_mean"], previous_target) - 1.0
    dataset["feature_coverage"] = dataset[list(MODEL_FEATURES)].notna().mean(axis=1)
    return dataset


def _add_cross_sectional_features(dataset: pd.DataFrame) -> pd.DataFrame:
    output = dataset.copy()
    for feature in MODEL_FEATURES:
        values = pd.to_numeric(output[feature], errors="coerce").replace([np.inf, -np.inf], np.nan)
        output[feature] = values
        output[f"z__{feature}"] = values.groupby(output["signal_date"]).transform(_robust_zscore)
        output[f"z__{feature}"] = output[f"z__{feature}"].fillna(0.0).clip(-5.0, 5.0)
    return output


def _robust_zscore(series: pd.Series) -> pd.Series:
    median = series.median(skipna=True)
    absolute = (series - median).abs()
    scale = 1.4826 * absolute.median(skipna=True)
    if not np.isfinite(scale) or scale < 1e-12:
        scale = series.std(skipna=True)
    if not np.isfinite(scale) or scale < 1e-12:
        return pd.Series(np.nan, index=series.index)
    return (series - median) / scale


def fit_weighted_ridge(
    frame: pd.DataFrame,
    config: RadarConfig,
    features: tuple[str, ...] = MODEL_FEATURES,
) -> RidgeModel:
    clean = frame.loc[frame["label_return"].notna()].copy()
    if clean.empty:
        raise ValueError("No labeled rows available for training.")
    clean["target"] = clean["label_return"] - clean.groupby("signal_date")[
        "label_return"
    ].transform("median")
    clean["target"] = clean.groupby("signal_date")["target"].transform(_winsorize)

    x = clean[[f"z__{feature}" for feature in features]].to_numpy(dtype=float)
    y = clean["target"].to_numpy(dtype=float)
    counts = clean.groupby("signal_date")["security_id"].transform("count").to_numpy(dtype=float)
    weights = 1.0 / counts
    weights *= len(weights) / weights.sum()
    design = np.column_stack([np.ones(len(x)), x])
    weighted_design = design * np.sqrt(weights)[:, None]
    weighted_target = y * np.sqrt(weights)
    penalty = np.eye(design.shape[1]) * config.ridge_alpha
    penalty[0, 0] = 0.0
    coefficients = np.linalg.solve(
        weighted_design.T @ weighted_design + penalty,
        weighted_design.T @ weighted_target,
    )
    return RidgeModel(
        intercept=float(coefficients[0]),
        coefficients={feature: float(value) for feature, value in zip(features, coefficients[1:])},
        train_rows=len(clean),
        train_dates=clean["signal_date"].nunique(),
    )


def _winsorize(series: pd.Series) -> pd.Series:
    if series.notna().sum() < 20:
        return series
    lower, upper = series.quantile([0.01, 0.99])
    return series.clip(lower=lower, upper=upper)


def walk_forward_backtest(
    dataset: pd.DataFrame,
    config: RadarConfig,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    eligible = dataset.loc[dataset["eligible"]].copy()
    test_dates = sorted(
        eligible.loc[eligible["label_date_usable"], "signal_date"].drop_duplicates().tolist()
    )
    results: list[dict[str, Any]] = []
    cost = config.transaction_cost_bps / 10_000.0
    for test_date in test_dates:
        test = eligible.loc[eligible["signal_date"] == test_date].copy()
        cutoff = test["decision_cutoff_utc"].iloc[0]
        train = eligible.loc[
            (eligible["signal_date"] < test_date)
            & eligible["label_date_usable"]
            & eligible["label_return"].notna()
            & (eligible["label_fetched_at"] <= cutoff)
        ].copy()
        train_dates = train["signal_date"].nunique()
        if train_dates < config.minimum_train_dates:
            continue
        model = fit_weighted_ridge(train, config)
        test["prediction"] = model.predict(test)
        test = test.sort_values(["prediction", "dollar_volume"], ascending=[False, False])
        selected = test.head(config.top_k)
        if len(selected) < config.top_k or selected["label_return"].isna().any():
            continue
        known = test.loc[test["label_return"].notna()]
        gross_return = float(selected["label_return"].mean())
        benchmark_return = float(known["label_return"].mean())
        information_coefficient = float(
            known["prediction"].rank(pct=True).corr(known["label_return"].rank(pct=True))
        )
        results.append(
            {
                "signal_date": test_date,
                "entry_date": selected["entry_date"].iloc[0],
                "train_dates": train_dates,
                "train_rows": len(train),
                "selected_count": len(selected),
                "gross_return": gross_return,
                "net_return": gross_return - cost,
                "benchmark_return": benchmark_return - cost,
                "excess_return": gross_return - benchmark_return,
                "hit_rate": float((selected["label_return"] > 0).mean()),
                "information_coefficient": information_coefficient,
                "symbols": ",".join(selected["symbol"].tolist()),
            }
        )
    backtest = pd.DataFrame(results)
    metrics = summarize_backtest(backtest)
    return backtest, metrics


def summarize_backtest(backtest: pd.DataFrame) -> dict[str, Any]:
    if backtest.empty:
        return {
            "backtest_days": 0,
            "warning": "Not enough strictly walk-forward dates for a backtest.",
        }
    portfolio_curve = (1.0 + backtest["net_return"]).cumprod()
    benchmark_curve = (1.0 + backtest["benchmark_return"]).cumprod()
    drawdown = portfolio_curve / portfolio_curve.cummax() - 1.0
    return {
        "backtest_days": int(len(backtest)),
        "first_signal_date": backtest["signal_date"].min().isoformat(),
        "last_signal_date": backtest["signal_date"].max().isoformat(),
        "top_k": int(backtest["selected_count"].iloc[0]),
        "cumulative_net_return": float(portfolio_curve.iloc[-1] - 1.0),
        "cumulative_benchmark_return": float(benchmark_curve.iloc[-1] - 1.0),
        "cumulative_excess_return": float(
            (portfolio_curve.iloc[-1] / benchmark_curve.iloc[-1]) - 1.0
        ),
        "average_daily_net_return": float(backtest["net_return"].mean()),
        "average_daily_excess_return": float(backtest["excess_return"].mean()),
        "positive_portfolio_days": float((backtest["net_return"] > 0).mean()),
        "average_selected_hit_rate": float(backtest["hit_rate"].mean()),
        "average_information_coefficient": float(backtest["information_coefficient"].mean()),
        "max_drawdown": float(drawdown.min()),
    }


def evaluate_deployment_gate(
    metrics: dict[str, Any],
    model: RidgeModel,
    feature_asof_violations: int,
) -> dict[str, Any]:
    checks = {
        "minimum_60_training_dates": model.train_dates >= 60,
        "minimum_20_backtest_dates": int(metrics.get("backtest_days", 0)) >= 20,
        "positive_net_return": float(metrics.get("cumulative_net_return", -1.0)) > 0,
        "positive_excess_return": float(metrics.get("cumulative_excess_return", -1.0)) > 0,
        "positive_rank_ic": float(metrics.get("average_information_coefficient", -1.0)) > 0,
        "zero_asof_violations": feature_asof_violations == 0,
    }
    passed = all(checks.values())
    return {
        "status": "paper_trade_candidate" if passed else "research_only",
        "passed": passed,
        "checks": checks,
        "failed_checks": [name for name, value in checks.items() if not value],
    }


def train_latest_radar(
    dataset: pd.DataFrame,
    config: RadarConfig,
) -> tuple[pd.DataFrame, RidgeModel]:
    latest_date = dataset["signal_date"].max()
    latest = dataset.loc[(dataset["signal_date"] == latest_date) & dataset["eligible"]].copy()
    cutoff = latest["decision_cutoff_utc"].iloc[0]
    train = dataset.loc[
        dataset["eligible"]
        & dataset["label_date_usable"]
        & dataset["label_return"].notna()
        & (dataset["label_fetched_at"] <= cutoff)
    ].copy()
    model = fit_weighted_ridge(train, config)
    latest["predicted_excess_return"] = model.predict(latest)
    latest["radar_score"] = latest["predicted_excess_return"].rank(pct=True) * 100.0
    latest["rank"] = latest["predicted_excess_return"].rank(method="first", ascending=False).astype(int)
    latest["reason"] = _explain_rows(latest, model)
    latest = latest.sort_values(["rank", "dollar_volume"])
    return latest, model


def _explain_rows(frame: pd.DataFrame, model: RidgeModel) -> pd.Series:
    coefficients = pd.Series(model.coefficients)
    explanations: list[str] = []
    for _, row in frame.iterrows():
        contributions = pd.Series(
            {
                feature: row[f"z__{feature}"] * coefficient
                for feature, coefficient in coefficients.items()
            }
        )
        positive = contributions.loc[contributions > 0].sort_values(ascending=False).head(3)
        chosen = positive if not positive.empty else contributions.abs().sort_values(ascending=False).head(3)
        explanations.append("、".join(FEATURE_LABELS[feature] for feature in chosen.index))
    return pd.Series(explanations, index=frame.index)


def write_radar_outputs(
    output_dir: Path,
    radar: pd.DataFrame,
    backtest: pd.DataFrame,
    audit: pd.DataFrame,
    model: RidgeModel,
    metrics: dict[str, Any],
    config: RadarConfig,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    signal_date = radar["signal_date"].max().isoformat()
    radar_path = output_dir / f"opportunity_radar_{signal_date}.csv"
    backtest_path = output_dir / f"opportunity_radar_backtest_{signal_date}.csv"
    audit_path = output_dir / f"opportunity_radar_audit_{signal_date}.csv"
    model_path = output_dir / f"opportunity_radar_model_{signal_date}.json"

    radar_columns = [
        "rank",
        "radar_score",
        "symbol",
        "company_name",
        "sector",
        "industry",
        "signal_date",
        "entry_date",
        "decision_cutoff_utc",
        "close",
        "dollar_volume",
        "predicted_excess_return",
        "feature_coverage",
        "ret_1d",
        "ret_3d",
        "target_upside",
        "recommendation_score",
        "q_eps_revision",
        "q_revenue_revision",
        "target_revision",
        "reason",
    ]
    feature_asof_violations = int(audit["feature_asof_violations"].sum())
    deployment_gate = evaluate_deployment_gate(metrics, model, feature_asof_violations)
    radar = radar.copy()
    radar["deployment_status"] = deployment_gate["status"]
    radar_columns.insert(1, "deployment_status")
    radar[radar_columns].to_csv(radar_path, index=False)
    backtest.to_csv(backtest_path, index=False)
    audit.to_csv(audit_path, index=False)

    warning = None
    if model.train_dates < 20:
        warning = (
            f"Only {model.train_dates} usable signal dates are available. "
            "The trained radar is experimental and its backtest is not statistically reliable."
        )
    payload = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "signal_date": signal_date,
        "entry_date": radar["entry_date"].iloc[0].isoformat(),
        "decision_cutoff_utc": radar["decision_cutoff_utc"].iloc[0].isoformat(),
        "config": asdict(config),
        "features": list(MODEL_FEATURES),
        "feature_labels": FEATURE_LABELS,
        "model": asdict(model),
        "backtest": metrics,
        "leakage_controls": {
            "price_rule": "Only bars with trade_date <= signal_date and fetched_at <= decision cutoff.",
            "snapshot_rule": "Only snapshots with fetched_at <= decision cutoff.",
            "execution_rule": "Signal after prior close; buy at next-session open; evaluate at that close.",
            "walk_forward_rule": "Training labels must have been fetched before each test decision cutoff.",
            "date_split_rule": "Expanding time split; no random row split.",
            "label_coverage_rule": config.minimum_label_coverage,
            "feature_asof_violations": feature_asof_violations,
        },
        "deployment_gate": deployment_gate,
        "warning": warning,
    }
    model_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "radar": radar_path,
        "backtest": backtest_path,
        "audit": audit_path,
        "model": model_path,
    }
