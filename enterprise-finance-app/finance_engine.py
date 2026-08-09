from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


CANONICAL_COLUMNS = [
    "company",
    "ticker",
    "fiscal_year",
    "revenue",
    "gross_profit",
    "operating_income",
    "net_income",
    "operating_cash_flow",
    "capex",
    "free_cash_flow",
    "cash",
    "total_debt",
    "diluted_shares",
    "share_price",
    "currency",
    "is_estimate",
    "source_note",
    "source_url",
]

REQUIRED_COLUMNS = ["company", "fiscal_year", "revenue"]

NUMERIC_COLUMNS = [
    "fiscal_year",
    "revenue",
    "gross_profit",
    "operating_income",
    "net_income",
    "operating_cash_flow",
    "capex",
    "free_cash_flow",
    "cash",
    "total_debt",
    "diluted_shares",
    "share_price",
]

COLUMN_ALIASES = {
    "公司": "company",
    "公司名称": "company",
    "股票代码": "ticker",
    "代码": "ticker",
    "财年": "fiscal_year",
    "年份": "fiscal_year",
    "营业收入": "revenue",
    "收入": "revenue",
    "营收": "revenue",
    "毛利润": "gross_profit",
    "毛利": "gross_profit",
    "营业利润": "operating_income",
    "经营利润": "operating_income",
    "净利润": "net_income",
    "经营现金流": "operating_cash_flow",
    "经营活动现金流": "operating_cash_flow",
    "资本开支": "capex",
    "资本支出": "capex",
    "自由现金流": "free_cash_flow",
    "现金": "cash",
    "现金及等价物": "cash",
    "总债务": "total_debt",
    "债务": "total_debt",
    "稀释后股数": "diluted_shares",
    "稀释股数": "diluted_shares",
    "股价": "share_price",
    "币种": "currency",
    "是否预测": "is_estimate",
    "预测": "is_estimate",
    "来源说明": "source_note",
    "来源链接": "source_url",
}


@dataclass(frozen=True)
class DataQualityReport:
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    filled_fcf_rows: int

    @property
    def ok(self) -> bool:
        return not self.errors


def normalize_financial_data(raw: pd.DataFrame) -> tuple[pd.DataFrame, DataQualityReport]:
    """Normalize an uploaded financial table into the app's canonical schema."""
    if raw is None or raw.empty:
        return pd.DataFrame(columns=CANONICAL_COLUMNS), DataQualityReport(
            ("文件没有数据行。",), (), 0
        )

    frame = raw.copy()
    frame.columns = [str(column).strip() for column in frame.columns]
    frame = frame.rename(
        columns={
            column: COLUMN_ALIASES.get(column, column.strip().lower())
            for column in frame.columns
        }
    )

    missing_required = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing_required:
        labels = "、".join(missing_required)
        return pd.DataFrame(columns=CANONICAL_COLUMNS), DataQualityReport(
            (f"缺少必填列：{labels}。请使用下载模板。",), (), 0
        )

    for column in CANONICAL_COLUMNS:
        if column not in frame.columns:
            frame[column] = np.nan

    frame = frame[CANONICAL_COLUMNS].copy()
    frame["company"] = frame["company"].fillna("").astype(str).str.strip()
    frame["ticker"] = frame["ticker"].fillna("").astype(str).str.strip().str.upper()
    frame["currency"] = (
        frame["currency"].fillna("USD").astype(str).str.strip().str.upper()
    )
    frame["source_note"] = frame["source_note"].fillna("").astype(str).str.strip()
    frame["source_url"] = frame["source_url"].fillna("").astype(str).str.strip()

    for column in NUMERIC_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    frame["is_estimate"] = frame["is_estimate"].map(_to_bool).fillna(False).astype(bool)

    errors: list[str] = []
    warnings: list[str] = []

    invalid_company = frame["company"].eq("")
    if invalid_company.any():
        errors.append(f"{int(invalid_company.sum())} 行缺少 company/公司。")

    invalid_year = frame["fiscal_year"].isna()
    if invalid_year.any():
        errors.append(f"{int(invalid_year.sum())} 行 fiscal_year/财年无法识别。")

    invalid_revenue = frame["revenue"].isna()
    if invalid_revenue.any():
        errors.append(f"{int(invalid_revenue.sum())} 行 revenue/营业收入无法识别。")

    nonpositive_revenue = frame["revenue"].notna() & frame["revenue"].le(0)
    if nonpositive_revenue.any():
        errors.append(f"{int(nonpositive_revenue.sum())} 行营业收入小于或等于 0。")

    duplicate_mask = frame.duplicated(["company", "fiscal_year"], keep=False)
    if duplicate_mask.any():
        errors.append(
            f"{int(duplicate_mask.sum())} 行出现重复的 company + fiscal_year 组合。"
        )

    fcf_missing = frame["free_cash_flow"].isna()
    fcf_can_fill = (
        fcf_missing
        & frame["operating_cash_flow"].notna()
        & frame["capex"].notna()
    )
    frame.loc[fcf_can_fill, "free_cash_flow"] = (
        frame.loc[fcf_can_fill, "operating_cash_flow"]
        - frame.loc[fcf_can_fill, "capex"].abs()
    )
    filled_fcf_rows = int(fcf_can_fill.sum())
    if filled_fcf_rows:
        warnings.append(
            f"已为 {filled_fcf_rows} 行按“经营现金流 − 资本开支绝对值”补算自由现金流。"
        )

    remaining_actual_fcf = int(
        (frame["free_cash_flow"].isna() & ~frame["is_estimate"]).sum()
    )
    if remaining_actual_fcf:
        warnings.append(
            f"{remaining_actual_fcf} 行实绩数据缺少自由现金流，相关指标将留空。"
        )

    unusual_currency = sorted(set(frame.loc[frame["currency"] != "USD", "currency"]))
    if unusual_currency:
        warnings.append(
            "检测到非 USD 币种。应用不会自动换汇，请确保同一公司所有金额单位一致。"
        )

    frame["fiscal_year"] = frame["fiscal_year"].round().astype("Int64")
    frame = frame.sort_values(["company", "fiscal_year"]).reset_index(drop=True)
    return frame, DataQualityReport(tuple(errors), tuple(warnings), filled_fcf_rows)


def enrich_financial_data(frame: pd.DataFrame) -> pd.DataFrame:
    """Add growth, margin, and incremental profitability calculations."""
    if frame.empty:
        return frame.copy()

    result = frame.sort_values(["company", "fiscal_year"]).copy()
    groups = result.groupby("company", sort=False)

    result["revenue_growth"] = groups["revenue"].pct_change(fill_method=None)
    result["gross_margin"] = _safe_divide(result["gross_profit"], result["revenue"])
    result["operating_margin"] = _safe_divide(
        result["operating_income"], result["revenue"]
    )
    result["net_margin"] = _safe_divide(result["net_income"], result["revenue"])
    result["fcf_margin"] = _safe_divide(result["free_cash_flow"], result["revenue"])
    result["net_income_growth"] = groups["net_income"].pct_change(fill_method=None)
    result["fcf_growth"] = groups["free_cash_flow"].pct_change(fill_method=None)

    revenue_change = groups["revenue"].diff()
    operating_income_change = groups["operating_income"].diff()
    net_income_change = groups["net_income"].diff()
    fcf_change = groups["free_cash_flow"].diff()
    result["incremental_operating_margin"] = _safe_divide(
        operating_income_change, revenue_change
    )
    result["incremental_net_margin"] = _safe_divide(
        net_income_change, revenue_change
    )
    result["incremental_fcf_margin"] = _safe_divide(fcf_change, revenue_change)
    result["growth_acceleration"] = groups["revenue_growth"].diff()
    result["rule_of_40"] = result["revenue_growth"] + result["fcf_margin"]
    return result


def calculate_cagr(
    start_value: float | int | None,
    end_value: float | int | None,
    years: float | int | None,
) -> float:
    if start_value is None or end_value is None or years is None:
        return np.nan
    if pd.isna(start_value) or pd.isna(end_value) or pd.isna(years):
        return np.nan
    if float(start_value) <= 0 or float(end_value) <= 0 or float(years) <= 0:
        return np.nan
    return (float(end_value) / float(start_value)) ** (1 / float(years)) - 1


def trailing_cagr(
    frame: pd.DataFrame, column: str, max_years: int = 3
) -> tuple[float, int]:
    clean = frame.dropna(subset=["fiscal_year", column]).sort_values("fiscal_year")
    if len(clean) < 2:
        return np.nan, 0
    end = clean.iloc[-1]
    eligible = clean[clean["fiscal_year"] >= int(end["fiscal_year"]) - max_years]
    start = eligible.iloc[0]
    years = int(end["fiscal_year"]) - int(start["fiscal_year"])
    return calculate_cagr(start[column], end[column], years), years


def required_future_value(
    current_value: float, required_return: float, holding_years: float
) -> float:
    if current_value <= 0:
        raise ValueError("当前估值必须大于 0。")
    if required_return <= -1:
        raise ValueError("要求回报率必须大于 -100%。")
    if holding_years <= 0:
        raise ValueError("持有年数必须大于 0。")
    return current_value * (1 + required_return) ** holding_years


def implied_growth_scenarios(
    *,
    target_enterprise_value: float,
    terminal_fcf_margin: float,
    base_revenue: float,
    growth_years: float,
    terminal_multiples: Iterable[float],
) -> pd.DataFrame:
    if target_enterprise_value <= 0:
        raise ValueError("目标企业价值必须大于 0。")
    if not 0 < terminal_fcf_margin <= 1:
        raise ValueError("终值自由现金流率必须在 0% 到 100% 之间。")
    if base_revenue <= 0:
        raise ValueError("基期收入必须大于 0。")
    if growth_years <= 0:
        raise ValueError("增长年数必须大于 0。")

    rows = []
    for multiple in terminal_multiples:
        multiple = float(multiple)
        if multiple <= 0:
            continue
        required_fcf = target_enterprise_value / multiple
        required_revenue = required_fcf / terminal_fcf_margin
        implied_cagr = calculate_cagr(base_revenue, required_revenue, growth_years)
        rows.append(
            {
                "terminal_fcf_multiple": multiple,
                "required_fcf": required_fcf,
                "required_revenue": required_revenue,
                "implied_revenue_cagr": implied_cagr,
            }
        )
    return pd.DataFrame(rows)


def enterprise_value_from_share_price(
    *, share_price: float, diluted_shares_m: float, cash_m: float, debt_m: float
) -> tuple[float, float]:
    """Return equity value and EV in USD billions from per-share and USD million inputs."""
    if share_price <= 0 or diluted_shares_m <= 0:
        raise ValueError("股价和稀释后股数必须大于 0。")
    equity_value_b = share_price * diluted_shares_m / 1_000
    enterprise_value_b = equity_value_b + debt_m / 1_000 - cash_m / 1_000
    return equity_value_b, enterprise_value_b


def target_ev_from_equity_return(
    *,
    current_equity_value_b: float,
    required_return: float,
    holding_years: float,
    terminal_net_debt_b: float,
) -> tuple[float, float]:
    target_equity_value_b = required_future_value(
        current_equity_value_b, required_return, holding_years
    )
    return target_equity_value_b, target_equity_value_b + terminal_net_debt_b


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    valid = denominator.notna() & denominator.ne(0)
    result = pd.Series(np.nan, index=denominator.index, dtype=float)
    result.loc[valid] = numerator.loc[valid] / denominator.loc[valid]
    return result.replace([np.inf, -np.inf], np.nan)


def _to_bool(value: object) -> bool | float:
    if pd.isna(value):
        return np.nan
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value).strip().lower()
    return normalized in {
        "1",
        "true",
        "yes",
        "y",
        "是",
        "预测",
        "estimate",
        "estimated",
    }
