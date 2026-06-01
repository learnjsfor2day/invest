"""Tier classification: explicit, quantitative rules.

Inputs: the latest earnings row + a few signals.
Output: tier (1-4), list of matched rules, human-readable reason.

Design: deterministic. Same inputs → same output. No LLM.

Tiers:
  1 = 重点跟踪    (>= 3 strong signals)
  2 = 等待验证    (1-2 signals)
  3 = 已反应充分  (no signals AND stock already up materially)
  4 = 噪音较大    (no signals AND no stock move)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


# --- thresholds (tweak in one place) ---
CLOUD_YOY_HIGH = 0.30           # +30% YoY
AI_ARR_YOY_HIGH = 0.50          # +50% YoY (very high bar — only the real runners)
BACKLOG_QOQ_HIGH = 0.20         # +20% QoQ
REVENUE_YOY_HIGH = 0.20         # +20% YoY
STOCK_RUNUP_3MO = 0.30          # 3-month return >= 30% → "已反应"


@dataclass
class TierInputs:
    revenue_yoy: Optional[float] = None
    cloud_revenue_yoy: Optional[float] = None
    ai_arr_yoy: Optional[float] = None
    backlog_rpo_qoq: Optional[float] = None
    capex_raised: Optional[bool] = None         # vs prior quarter's guidance
    capacity_constrained: Optional[bool] = None  # explicit mgmt language
    stock_runup_3mo: Optional[float] = None      # 0.50 = +50%


@dataclass
class TierResult:
    tier: int
    rule_matches: list[str] = field(default_factory=list)
    reason: str = ""


def classify(inputs: TierInputs) -> TierResult:
    matches: list[str] = []

    if inputs.cloud_revenue_yoy is not None and inputs.cloud_revenue_yoy >= CLOUD_YOY_HIGH:
        matches.append(f"cloud_yoy>={int(CLOUD_YOY_HIGH*100)}% (actual {inputs.cloud_revenue_yoy*100:.0f}%)")
    if inputs.ai_arr_yoy is not None and inputs.ai_arr_yoy >= AI_ARR_YOY_HIGH:
        matches.append(f"ai_arr_yoy>={int(AI_ARR_YOY_HIGH*100)}% (actual {inputs.ai_arr_yoy*100:.0f}%)")
    if inputs.backlog_rpo_qoq is not None and inputs.backlog_rpo_qoq >= BACKLOG_QOQ_HIGH:
        matches.append(f"backlog_qoq>={int(BACKLOG_QOQ_HIGH*100)}% (actual {inputs.backlog_rpo_qoq*100:.0f}%)")
    if inputs.revenue_yoy is not None and inputs.revenue_yoy >= REVENUE_YOY_HIGH:
        matches.append(f"revenue_yoy>={int(REVENUE_YOY_HIGH*100)}% (actual {inputs.revenue_yoy*100:.0f}%)")
    if inputs.capex_raised:
        matches.append("capex_raised")
    if inputs.capacity_constrained:
        matches.append("capacity_constrained_quote")

    score = len(matches)

    if score >= 3:
        return TierResult(1, matches, f"{score} 个硬信号同步触发")
    if score >= 1:
        return TierResult(2, matches, f"{score} 个信号,需下季度验证")
    # No fundamental signal — separate "已反应" from "噪音"
    if inputs.stock_runup_3mo is not None and inputs.stock_runup_3mo >= STOCK_RUNUP_3MO:
        return TierResult(
            3, matches,
            f"无新基本面信号但 3 月涨幅 {inputs.stock_runup_3mo*100:.0f}% — 已反应"
        )
    return TierResult(4, matches, "无量化信号且股价未表现 — 暂列噪音/证据不足")


def inputs_from_earnings(row: dict, prior_row: Optional[dict] = None,
                         capacity_constrained: Optional[bool] = None,
                         stock_runup_3mo: Optional[float] = None) -> TierInputs:
    """Build TierInputs from an earnings dict (and optional prior-quarter row).

    capex_raised is derived by comparing capex_full_year_low to prior quarter's
    same field (if prior available). capacity_constrained should be passed in
    from LLM extraction (extract.signals['capacity_constrained']).
    """
    capex_raised = None
    if prior_row and prior_row.get("capex_full_year_low") and row.get("capex_full_year_low"):
        try:
            capex_raised = float(row["capex_full_year_low"]) > float(prior_row["capex_full_year_low"])
        except (TypeError, ValueError):
            capex_raised = None
    return TierInputs(
        revenue_yoy=row.get("revenue_yoy"),
        cloud_revenue_yoy=row.get("cloud_revenue_yoy"),
        ai_arr_yoy=row.get("ai_arr_yoy"),
        backlog_rpo_qoq=row.get("backlog_rpo_qoq"),
        capex_raised=capex_raised,
        capacity_constrained=capacity_constrained,
        stock_runup_3mo=stock_runup_3mo,
    )
