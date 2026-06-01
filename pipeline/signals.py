"""Price/volume anomaly scanner — sector-agnostic leading indicators.

Computes 4 anomaly types per ticker on any given day:

  vol_spike      : today_volume / 20d_avg_volume >= 2.5
  rs_top         : 3-month total return rank in top decile of universe (vs SPY)
  squeeze_break  : ATR_20 / ATR_100 < 0.6 AND close > prior 20d high
  high_52w       : new 252-day high AND volume > 2x 20d avg

IV anomaly is intentionally omitted in v1: yfinance's options chain is
slow per-ticker and noisy. Add later if needed.

Data: yfinance (free). Output: writes hits to the `signals` table; returns
a summary list for the calling scanner.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

from . import db


# ---- thresholds (tweak in one place) ----
VOL_SPIKE_RATIO = 2.5            # today vs 20d
RS_TOP_PCT = 0.10                # top decile
SQUEEZE_RATIO = 0.6              # ATR_20 / ATR_100
HIGH_52W_VOL_RATIO = 2.0         # volume must be >= 2x to qualify

LOOKBACK_DAYS = 260              # ~1 year trading days


@dataclass
class SignalHit:
    ticker: str
    signal_type: str
    trade_date: str
    score: float
    raw: dict


def _atr(df, n: int) -> Optional[float]:
    """Average True Range over last n bars (Wilder-ish, simple mean for speed)."""
    if df is None or len(df) < n + 1:
        return None
    high = df["High"].tail(n).to_numpy()
    low = df["Low"].tail(n).to_numpy()
    close_prev = df["Close"].shift(1).tail(n).to_numpy()
    tr = [max(h - l, abs(h - cp), abs(l - cp))
          for h, l, cp in zip(high, low, close_prev)
          if not (math.isnan(h) or math.isnan(l) or math.isnan(cp))]
    if not tr:
        return None
    return sum(tr) / len(tr)


def _scan_one(ticker: str, df, spy_3m_return: float) -> list[SignalHit]:
    """Compute all signals for one ticker. Requires >= 60 bars of OHLCV."""
    hits: list[SignalHit] = []
    if df is None or len(df) < 60:
        return hits

    # Drop incomplete rows
    df = df.dropna(subset=["Close", "Volume"])
    if len(df) < 60:
        return hits

    last = df.iloc[-1]
    trade_date = df.index[-1].strftime("%Y-%m-%d")
    close = float(last["Close"])
    vol = float(last["Volume"])

    # vol_spike
    avg20 = float(df["Volume"].tail(20).mean())
    if avg20 > 0:
        ratio = vol / avg20
        if ratio >= VOL_SPIKE_RATIO:
            hits.append(SignalHit(
                ticker, "vol_spike", trade_date, score=ratio,
                raw={"vol": vol, "avg20": avg20, "ratio": round(ratio, 2),
                     "close": close},
            ))

    # rs_top — caller fills, see scan_universe (we just compute the 3m return here)
    # squeeze_break
    atr20 = _atr(df, 20)
    atr100 = _atr(df, 100) if len(df) >= 101 else None
    if atr20 and atr100 and atr100 > 0:
        sq = atr20 / atr100
        prior20_high = float(df["High"].iloc[-21:-1].max()) if len(df) >= 21 else None
        if sq < SQUEEZE_RATIO and prior20_high and close > prior20_high:
            hits.append(SignalHit(
                ticker, "squeeze_break", trade_date,
                score=(SQUEEZE_RATIO - sq) / SQUEEZE_RATIO,
                raw={"atr20": atr20, "atr100": atr100, "sq_ratio": round(sq, 3),
                     "close": close, "prior20_high": prior20_high},
            ))

    # high_52w
    if len(df) >= 252:
        high_252 = float(df["High"].iloc[-252:-1].max())
        if close > high_252 and avg20 > 0 and vol / avg20 >= HIGH_52W_VOL_RATIO:
            hits.append(SignalHit(
                ticker, "high_52w", trade_date,
                score=vol / avg20,
                raw={"close": close, "prior_252d_high": high_252,
                     "vol_ratio": round(vol / avg20, 2)},
            ))

    return hits


def _three_month_return(df) -> Optional[float]:
    if df is None or len(df) < 64:
        return None
    closes = df["Close"].dropna()
    if len(closes) < 64:
        return None
    return float(closes.iloc[-1] / closes.iloc[-64] - 1)


def scan_universe(tickers: list[str], persist: bool = True) -> list[SignalHit]:
    """Download OHLCV for tickers + SPY, compute signals, optionally persist.

    Returns list of all hits (sorted by trade_date desc, score desc).
    """
    try:
        import yfinance as yf  # type: ignore
    except ImportError:
        print("[signals] yfinance not installed — pip install yfinance")
        return []

    universe = sorted(set(tickers) | {"SPY"})
    print(f"[signals] downloading {len(universe)} tickers, lookback={LOOKBACK_DAYS}d")
    raw = yf.download(
        universe, period=f"{LOOKBACK_DAYS}d", interval="1d",
        auto_adjust=False, group_by="ticker", progress=False, threads=True,
    )
    if raw is None or raw.empty:
        print("[signals] no data returned")
        return []

    # Per-ticker frames
    def frame_for(t: str):
        try:
            f = raw[t] if (t in raw.columns.get_level_values(0)) else None
        except Exception:
            f = None
        if f is None or f.empty:
            return None
        return f

    spy_df = frame_for("SPY")
    spy_3m = _three_month_return(spy_df) if spy_df is not None else 0.0
    if spy_3m is None:
        spy_3m = 0.0

    # First pass: scan all signals except rs_top, also collect 3m excess returns
    all_hits: list[SignalHit] = []
    excess: list[tuple[str, float, str, float]] = []  # (ticker, excess_3m, trade_date, close)
    for t in tickers:
        if t == "SPY":
            continue
        df = frame_for(t)
        all_hits.extend(_scan_one(t, df, spy_3m))
        if df is not None and len(df) >= 64:
            r3 = _three_month_return(df)
            if r3 is not None:
                excess.append((t, r3 - spy_3m, df.index[-1].strftime("%Y-%m-%d"),
                               float(df["Close"].iloc[-1])))

    # rs_top — top decile by excess return vs SPY
    excess.sort(key=lambda x: x[1], reverse=True)
    cutoff_n = max(1, int(len(excess) * RS_TOP_PCT))
    for t, ex, td, close in excess[:cutoff_n]:
        all_hits.append(SignalHit(
            t, "rs_top", td, score=ex,
            raw={"excess_3m": round(ex, 4), "spy_3m": round(spy_3m, 4),
                 "close": close, "rank": "top10pct"},
        ))

    # Persist
    if persist:
        new_count = 0
        for h in all_hits:
            if db.record_signal(h.ticker, h.signal_type, h.trade_date,
                                h.score, h.raw):
                new_count += 1
        print(f"[signals] {len(all_hits)} hits, {new_count} new (rest already recorded)")

    all_hits.sort(key=lambda h: (h.trade_date, h.score), reverse=True)
    return all_hits


def latest_hits_summary(hits: Iterable[SignalHit]) -> dict[str, list[SignalHit]]:
    """Group hits by ticker for printing."""
    by_ticker: dict[str, list[SignalHit]] = {}
    for h in hits:
        by_ticker.setdefault(h.ticker, []).append(h)
    return by_ticker
