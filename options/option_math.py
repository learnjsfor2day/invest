from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Literal


OptionType = Literal["call", "put"]
Action = Literal["buy", "sell"]


@dataclass(frozen=True)
class Greeks:
    price: float
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float


@dataclass(frozen=True)
class OptionLeg:
    action: Action
    option_type: OptionType
    strike: float
    contracts: int
    premium: float


def norm_pdf(value: float) -> float:
    return math.exp(-(value * value) / 2) / math.sqrt(2 * math.pi)


def norm_cdf(value: float) -> float:
    return 0.5 * (1 + math.erf(value / math.sqrt(2)))


def dte(expiry: date, today: date | None = None) -> int:
    base = today or date.today()
    return max(0, (expiry - base).days)


def black_scholes(
    spot: float,
    strike: float,
    days_to_expiry: int | float,
    rate_pct: float,
    iv_pct: float,
    option_type: OptionType,
) -> Greeks:
    t = max(float(days_to_expiry), 0.0) / 365
    rate = float(rate_pct) / 100
    sigma = max(float(iv_pct) / 100, 0.0)
    spot = max(float(spot), 0.000001)
    strike = max(float(strike), 0.000001)
    if t <= 0 or sigma <= 0:
        intrinsic = option_intrinsic(spot, strike, option_type)
        return Greeks(price=intrinsic, delta=0.0, gamma=0.0, theta=0.0, vega=0.0, rho=0.0)

    sqrt_t = math.sqrt(t)
    d1 = (math.log(spot / strike) + (rate + sigma * sigma / 2) * t) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    nd1 = norm_pdf(d1)
    if option_type == "call":
        price = spot * norm_cdf(d1) - strike * math.exp(-rate * t) * norm_cdf(d2)
        delta = norm_cdf(d1)
        theta = (-spot * nd1 * sigma / (2 * sqrt_t) - rate * strike * math.exp(-rate * t) * norm_cdf(d2)) / 365
        rho = strike * t * math.exp(-rate * t) * norm_cdf(d2) / 100
    else:
        price = strike * math.exp(-rate * t) * norm_cdf(-d2) - spot * norm_cdf(-d1)
        delta = norm_cdf(d1) - 1
        theta = (-spot * nd1 * sigma / (2 * sqrt_t) + rate * strike * math.exp(-rate * t) * norm_cdf(-d2)) / 365
        rho = -strike * t * math.exp(-rate * t) * norm_cdf(-d2) / 100
    gamma = nd1 / (spot * sigma * sqrt_t)
    vega = spot * nd1 * sqrt_t / 100
    return Greeks(price=price, delta=delta, gamma=gamma, theta=theta, vega=vega, rho=rho)


def implied_volatility(
    market_price: float,
    spot: float,
    strike: float,
    days_to_expiry: int | float,
    rate_pct: float,
    option_type: OptionType,
    low: float = 1.0,
    high: float = 500.0,
) -> float:
    market_price = max(float(market_price), 0.0)
    lo = low / 100
    hi = high / 100
    for _ in range(80):
        mid = (lo + hi) / 2
        price = black_scholes(spot, strike, days_to_expiry, rate_pct, mid * 100, option_type).price
        if price > market_price:
            hi = mid
        else:
            lo = mid
    return (lo + hi) * 50


def required_spot_for_premium(
    target_premium: float,
    current_spot: float,
    strike: float,
    days_to_expiry: int | float,
    rate_pct: float,
    iv_pct: float,
    option_type: OptionType,
) -> float | None:
    """Find the underlying price that makes the option worth target_premium.

    The result assumes IV and rates stay unchanged. It is meant for planning
    stop/take-profit triggers, not for precise execution.
    """
    target = max(float(target_premium), 0.0)
    low = 0.01
    high = max(float(current_spot), float(strike), 1.0) * 3

    def price_at(spot: float) -> float:
        return black_scholes(spot, strike, days_to_expiry, rate_pct, iv_pct, option_type).price

    if option_type == "call":
        while price_at(high) < target and high < max(current_spot, strike) * 20:
            high *= 1.5
        if price_at(high) < target:
            return None
        for _ in range(80):
            mid = (low + high) / 2
            if price_at(mid) >= target:
                high = mid
            else:
                low = mid
        return (low + high) / 2

    if price_at(low) < target:
        return None
    while price_at(high) > target and high < max(current_spot, strike) * 20:
        high *= 1.5
    if price_at(high) > target:
        return None
    for _ in range(80):
        mid = (low + high) / 2
        if price_at(mid) >= target:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def option_intrinsic(spot: float, strike: float, option_type: OptionType) -> float:
    if option_type == "call":
        return max(0.0, spot - strike)
    return max(0.0, strike - spot)


def breakeven(strike: float, premium: float, option_type: OptionType) -> float:
    return strike + premium if option_type == "call" else strike - premium


def theta_pct(theta: float, premium: float) -> float:
    return abs(theta) / premium * 100 if premium > 0 else 0.0


def vega_pct(vega: float, premium: float) -> float:
    return vega / premium * 100 if premium > 0 else 0.0


def score_delta(abs_delta: float) -> str:
    if 0.30 <= abs_delta <= 0.65:
        return "green"
    if 0.15 <= abs_delta < 0.30 or 0.65 < abs_delta <= 0.85:
        return "yellow"
    return "red"


def score_theta_pct(value: float) -> str:
    if value < 1:
        return "green"
    if value < 3:
        return "yellow"
    return "red"


def score_vega_pct(value: float) -> str:
    if value < 3:
        return "green"
    if value < 5:
        return "yellow"
    return "red"


def score_dte(days_to_expiry: int | float) -> str:
    if 30 <= days_to_expiry <= 90:
        return "green"
    if 14 <= days_to_expiry < 30 or 90 < days_to_expiry <= 180:
        return "yellow"
    return "red"


def score_iv_rank(iv_rank: float) -> str:
    if iv_rank < 30:
        return "green"
    if iv_rank < 60:
        return "yellow"
    return "red"


def aggregate_score(scores: dict[str, str]) -> str:
    red = sum(1 for value in scores.values() if value == "red")
    yellow = sum(1 for value in scores.values() if value == "yellow")
    if red >= 2:
        return "red"
    if red >= 1 or yellow >= 3:
        return "yellow"
    return "green"


def scenario_matrix(
    spot: float,
    strike: float,
    premium: float,
    days_to_expiry: int,
    rate_pct: float,
    iv_pct: float,
    option_type: OptionType,
    moves: list[float] | None = None,
    time_ratios: list[float] | None = None,
) -> list[dict[str, float | str]]:
    moves = moves or [-15, -10, -5, 0, 5, 10, 15]
    time_ratios = time_ratios or [1.0, 0.66, 0.33, 0.0]
    output: list[dict[str, float | str]] = []
    for move in moves:
        scenario_spot = spot * (1 + move / 100)
        row: dict[str, float | str] = {"标的价格": scenario_spot, "涨跌幅": move}
        for ratio in time_ratios:
            remaining_days = round(days_to_expiry * ratio)
            if remaining_days <= 0:
                value = option_intrinsic(scenario_spot, strike, option_type)
                label = "到期"
            else:
                value = black_scholes(scenario_spot, strike, remaining_days, rate_pct, iv_pct, option_type).price
                label = f"{remaining_days}天"
            pnl = value - premium
            row[f"{label} 理论价"] = value
            row[f"{label} 盈亏%"] = pnl / premium * 100 if premium > 0 else 0
        output.append(row)
    return output


def strategy_payoff_at_expiry(spot: float, legs: list[OptionLeg]) -> float:
    total = 0.0
    for leg in legs:
        sign = 1 if leg.action == "buy" else -1
        intrinsic = option_intrinsic(spot, leg.strike, leg.option_type)
        total += sign * (intrinsic - leg.premium) * leg.contracts
    return total


def strategy_metrics(
    spot: float,
    legs: list[OptionLeg],
    scan_low_ratio: float = 0.4,
    scan_high_ratio: float = 1.8,
    points: int = 500,
) -> dict[str, object]:
    min_spot = max(0.01, spot * scan_low_ratio)
    max_spot = max(spot * scan_high_ratio, min_spot + 0.01)
    step = (max_spot - min_spot) / points
    prices = [min_spot + step * i for i in range(points + 1)]
    payoffs = [strategy_payoff_at_expiry(price, legs) for price in prices]
    breakevens: list[float] = []
    for left_price, right_price, left_payoff, right_payoff in zip(prices, prices[1:], payoffs, payoffs[1:], strict=False):
        if left_payoff == 0:
            breakevens.append(left_price)
        if left_payoff * right_payoff < 0:
            weight = abs(left_payoff) / (abs(left_payoff) + abs(right_payoff))
            breakevens.append(left_price + (right_price - left_price) * weight)
    net_debit = sum((1 if leg.action == "buy" else -1) * leg.premium * leg.contracts for leg in legs)
    return {
        "net_debit": net_debit,
        "max_profit": max(payoffs),
        "max_loss": min(payoffs),
        "breakevens": breakevens,
        "curve": [{"标的价格": price, "每股盈亏": payoff, "每组合盈亏": payoff * 100} for price, payoff in zip(prices, payoffs, strict=False)],
    }
