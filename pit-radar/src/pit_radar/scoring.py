"""Shared numeric and scoring helpers for the pit-radar radar modules.

Historically each of ``valuation_radar``, ``inflection_radar`` and
``opportunity_radar`` carried its own copy of small numeric helpers
(ratio, positive ratio, finite-check, sector percentile, weighted score,
utc coercion, ...). The copies drifted (see ``ratio``'s denominator
threshold below) and one module even reached across to another via a
private name (``inflection_radar`` calling ``valuation_radar._sector_percentile``).

This module collects a single, tested version of each helper so the
radar modules can stay focused on their own scoring pipelines. Every
symbol here is public; the radar modules re-export the ones they used
to define locally to preserve backwards compatibility for existing
imports (including tests that reach for ``_sector_percentile``).

Denominator semantics: ``ratio`` uses ``|denominator| > 1e-12`` to mask
near-zero denominators. The older ``inflection_radar._ratio`` only masked
exact zeros, which let tiny denominators produce blown-up ratios. We keep
the safer variant everywhere.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd


# --------------------------------------------------------------------- #
# Timezone / scalar helpers
# --------------------------------------------------------------------- #


def ensure_utc(value: datetime) -> datetime:
    """Return ``value`` in UTC; naive datetimes are treated as already UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def is_finite(value: object) -> bool:
    """True if ``value`` is a real, finite number (not NaN/inf/None/str)."""
    try:
        return bool(pd.notna(value) and np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False


def is_positive(value: object) -> bool:
    return is_finite(value) and float(value) > 0


def finite_float(value: object) -> float | None:
    return float(value) if is_finite(value) else None


def mean_or_none(values: list[float]) -> float | None:
    return float(np.mean(values)) if values else None


# --------------------------------------------------------------------- #
# Series helpers
# --------------------------------------------------------------------- #


def ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Element-wise ``numerator / denominator`` with a numeric-coerce and a
    near-zero denominator mask (``|d| > 1e-12``)."""
    numerator = pd.to_numeric(numerator, errors="coerce")
    denominator = pd.to_numeric(denominator, errors="coerce")
    return numerator / denominator.where(denominator.abs() > 1e-12)


def positive_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """``ratio`` restricted to strictly-positive numerator and denominator."""
    result = ratio(numerator, denominator)
    return result.where((numerator > 0) & (denominator > 0))


def scaled_change(
    current: pd.Series,
    prior: pd.Series,
    denominator_floor: float,
) -> pd.Series:
    """Percentage change with a floor on |prior| to damp small-base blow-ups,
    then clipped to [-3, 3]."""
    current = pd.to_numeric(current, errors="coerce")
    prior = pd.to_numeric(prior, errors="coerce")
    denominator = prior.abs().clip(lower=denominator_floor)
    return ((current - prior) / denominator).clip(-3.0, 3.0)


def as_bool(values: pd.Series) -> pd.Series:
    if values.dtype == bool:
        return values
    return values.astype(str).str.lower().isin({"true", "1", "yes"})


# --------------------------------------------------------------------- #
# Percentile / weighted score / reason helpers
# --------------------------------------------------------------------- #


def global_percentile(values: pd.Series, higher_better: bool) -> pd.Series:
    """Percentile rank across all rows (``ascending`` follows ``higher_better``)."""
    return values.rank(pct=True, ascending=higher_better)


def sector_percentile(
    frame: pd.DataFrame,
    column: str,
    higher_better: bool,
    minimum_sector_size: int,
) -> pd.Series:
    """Percentile rank within ``sector``; falls back to global rank when the
    sector has fewer than ``minimum_sector_size`` non-null observations."""
    values = pd.to_numeric(frame[column], errors="coerce").replace(
        [np.inf, -np.inf], np.nan
    )
    global_rank = global_percentile(values, higher_better)
    sector_rank = values.groupby(frame["sector"]).rank(pct=True, ascending=higher_better)
    counts = values.notna().groupby(frame["sector"]).transform("sum")
    return sector_rank.where(counts >= minimum_sector_size, global_rank)


def weighted_score(frame: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """Weighted mean of the columns in ``weights``; ignores missing components
    per-row and renormalises by the weight of the present components."""
    numerator = pd.Series(0.0, index=frame.index)
    denominator = pd.Series(0.0, index=frame.index)
    for column, weight in weights.items():
        available = frame[column].notna()
        numerator += frame[column].fillna(0.0) * weight
        denominator += available.astype(float) * weight
    return numerator / denominator.where(denominator > 0)


def top_components(components: dict[str, Any], k: int = 3) -> list[str]:
    """Return the top-``k`` component names ordered by (finite) value desc."""
    valid = [(name, float(value)) for name, value in components.items() if pd.notna(value)]
    return [name for name, _ in sorted(valid, key=lambda item: item[1], reverse=True)[:k]]


__all__ = [
    "as_bool",
    "ensure_utc",
    "finite_float",
    "global_percentile",
    "is_finite",
    "is_positive",
    "mean_or_none",
    "positive_ratio",
    "ratio",
    "scaled_change",
    "sector_percentile",
    "top_components",
    "weighted_score",
]
