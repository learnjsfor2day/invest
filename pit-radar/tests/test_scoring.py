"""Contract tests for the shared radar scoring helpers.

These pin down the small behaviors that used to live as private
copies inside ``valuation_radar`` / ``inflection_radar`` /
``opportunity_radar`` — including the ``|denom| > 1e-12`` guard that
distinguishes ``scoring.ratio`` from a naive divide.
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone

import math

import numpy as np
import pandas as pd
import pytest

from pit_radar import scoring


# --------------------------------------------------------------------- #
# Scalar helpers
# --------------------------------------------------------------------- #


def test_ensure_utc_treats_naive_as_utc_and_converts_aware() -> None:
    naive = datetime(2026, 7, 14, 9, 30)
    aware_eastern = datetime(2026, 7, 14, 9, 30, tzinfo=timezone(pd.Timedelta(hours=-4)))

    assert scoring.ensure_utc(naive).tzinfo is UTC
    assert scoring.ensure_utc(aware_eastern).utcoffset().total_seconds() == 0


@pytest.mark.parametrize(
    "value, expected",
    [
        (1.0, True),
        (0, True),
        (-3.5, True),
        (float("nan"), False),
        (float("inf"), False),
        (None, False),
        ("abc", False),
    ],
)
def test_is_finite(value: object, expected: bool) -> None:
    assert scoring.is_finite(value) is expected


def test_is_positive_matches_finite_and_strictly_positive() -> None:
    assert scoring.is_positive(0.01)
    assert not scoring.is_positive(0.0)
    assert not scoring.is_positive(-1.0)
    assert not scoring.is_positive(float("nan"))


def test_finite_float_returns_none_for_non_finite() -> None:
    assert scoring.finite_float("2.5") == 2.5
    assert scoring.finite_float(float("nan")) is None
    assert scoring.finite_float(None) is None


def test_mean_or_none_returns_none_for_empty() -> None:
    assert scoring.mean_or_none([]) is None
    assert scoring.mean_or_none([1.0, 3.0]) == 2.0


# --------------------------------------------------------------------- #
# Series helpers
# --------------------------------------------------------------------- #


def test_ratio_masks_near_zero_denominator() -> None:
    numerator = pd.Series([2.0, 4.0, 5.0])
    denominator = pd.Series([2.0, 1e-15, 0.0])

    result = scoring.ratio(numerator, denominator)

    # denominator=2 -> 1.0; the |d|<=1e-12 rows are NaN, not inf.
    assert result.iloc[0] == pytest.approx(1.0)
    assert pd.isna(result.iloc[1])
    assert pd.isna(result.iloc[2])


def test_ratio_coerces_string_inputs() -> None:
    result = scoring.ratio(pd.Series(["10", "bad"]), pd.Series(["5", "5"]))

    assert result.iloc[0] == pytest.approx(2.0)
    assert pd.isna(result.iloc[1])


def test_positive_ratio_masks_non_positive_operands() -> None:
    numerator = pd.Series([4.0, -1.0, 2.0, 0.0])
    denominator = pd.Series([2.0, 2.0, -2.0, 5.0])

    result = scoring.positive_ratio(numerator, denominator)

    assert result.iloc[0] == pytest.approx(2.0)
    assert result.iloc[1:].isna().all()


def test_scaled_change_clips_and_floors_denominator() -> None:
    current = pd.Series([12.0, 5.0, 5.0])
    prior = pd.Series([10.0, 0.01, 0.0])  # tiny + zero should be floored

    result = scoring.scaled_change(current, prior, denominator_floor=1.0)

    # 12/10 change is well under the clip
    assert result.iloc[0] == pytest.approx(0.2)
    # (5 - 0.01)/max(0.01, 1.0) = 4.99, but clipped to 3.0
    assert result.iloc[1] == pytest.approx(3.0)
    assert result.iloc[2] == pytest.approx(3.0)


def test_as_bool_handles_strings_and_native_bool() -> None:
    strings = pd.Series(["true", "False", "1", "no", "YES"])
    booleans = pd.Series([True, False, True])

    assert scoring.as_bool(strings).tolist() == [True, False, True, False, True]
    assert scoring.as_bool(booleans).tolist() == [True, False, True]


# --------------------------------------------------------------------- #
# Percentile / weighted score / top components
# --------------------------------------------------------------------- #


def test_global_percentile_orders_by_higher_better_flag() -> None:
    values = pd.Series([10.0, 20.0, 30.0])

    higher_top = scoring.global_percentile(values, higher_better=True)
    lower_top = scoring.global_percentile(values, higher_better=False)

    assert higher_top.iloc[-1] == 1.0
    assert lower_top.iloc[0] == 1.0


def test_sector_percentile_falls_back_to_global_when_sector_is_too_small() -> None:
    # Tech has 3 members, Health has 1. With minimum_sector_size=2, Health
    # must fall back to the global rank instead of getting sector-only rank.
    frame = pd.DataFrame(
        {
            "sector": ["Tech", "Tech", "Tech", "Health"],
            "pe": [10.0, 20.0, 30.0, 5.0],
        }
    )

    result = scoring.sector_percentile(frame, "pe", higher_better=False, minimum_sector_size=2)

    # Tech uses sector rank (lower pe → higher percentile). 10 → 1.0, 30 → 1/3.
    assert result.iloc[0] == pytest.approx(1.0)
    assert result.iloc[2] == pytest.approx(1 / 3)
    # Health falls back to the global rank of pe=5 (lowest globally → 1.0).
    assert result.iloc[3] == pytest.approx(1.0)


def test_weighted_score_renormalises_by_present_weights() -> None:
    frame = pd.DataFrame(
        {"a": [80.0, np.nan], "b": [60.0, 40.0]}
    )
    weights = {"a": 0.75, "b": 0.25}

    result = scoring.weighted_score(frame, weights)

    # row 0 has both components: 80*.75 + 60*.25 = 75
    assert result.iloc[0] == pytest.approx(75.0)
    # row 1 only has b, so the score is just 40 (weights renormalised).
    assert result.iloc[1] == pytest.approx(40.0)


def test_weighted_score_returns_nan_when_no_components_present() -> None:
    frame = pd.DataFrame({"a": [np.nan], "b": [np.nan]})
    weights = {"a": 0.5, "b": 0.5}

    assert pd.isna(scoring.weighted_score(frame, weights).iloc[0])


def test_top_components_returns_finite_only_ranked_desc() -> None:
    components = {"alpha": 50.0, "beta": float("nan"), "gamma": 80.0, "delta": 65.0}

    assert scoring.top_components(components, k=2) == ["gamma", "delta"]
    assert scoring.top_components(components, k=10) == ["gamma", "delta", "alpha"]


# --------------------------------------------------------------------- #
# Radar modules re-export the helpers under their old private names
# --------------------------------------------------------------------- #


def test_valuation_radar_still_exposes_legacy_private_aliases() -> None:
    # `tests/test_valuation_radar.py` imports these by their old names.
    from pit_radar.valuation_radar import (
        _ensure_utc,
        _global_percentile,
        _positive_ratio,
        _ratio,
        _sector_percentile,
        _top_components,
        _weighted_score,
    )

    assert _sector_percentile is scoring.sector_percentile
    assert _weighted_score is scoring.weighted_score
    assert _ratio is scoring.ratio
    assert _positive_ratio is scoring.positive_ratio
    assert _global_percentile is scoring.global_percentile
    assert _ensure_utc is scoring.ensure_utc
    assert _top_components is scoring.top_components


def test_inflection_radar_still_exposes_legacy_private_aliases() -> None:
    from pit_radar.inflection_radar import (
        _as_bool,
        _ensure_utc,
        _finite,
        _finite_float,
        _positive,
        _positive_ratio,
        _ratio,
        _scaled_change,
    )

    assert _ensure_utc is scoring.ensure_utc
    assert _ratio is scoring.ratio
    assert _positive_ratio is scoring.positive_ratio
    assert _scaled_change is scoring.scaled_change
    assert _finite is scoring.is_finite
    assert _positive is scoring.is_positive
    assert _finite_float is scoring.finite_float
    assert _as_bool is scoring.as_bool


def test_opportunity_radar_safe_ratio_is_shared_helper() -> None:
    from pit_radar.opportunity_radar import _safe_ratio

    assert _safe_ratio is scoring.ratio
