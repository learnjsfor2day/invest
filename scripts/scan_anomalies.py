"""Daily anomaly scan: scan watchlist for vol_spike / rs_top / squeeze_break /
high_52w. Persist hits to DB. Print today's results grouped by ticker.

Usage:
    python scripts/scan_anomalies.py            # us_tradable=true on watchlist
    python scripts/scan_anomalies.py NVDA AVGO  # specific tickers
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import db, signals  # noqa: E402


SIGNAL_LABELS = {
    "vol_spike":     "量比",
    "rs_top":        "RS",
    "squeeze_break": "Squeeze",
    "high_52w":      "52w新高",
}


def main() -> None:
    db.init_db()
    if len(sys.argv) > 1:
        tickers = [t.upper() for t in sys.argv[1:]]
    else:
        rows = db.list_companies(us_tradable_only=True)
        tickers = [r["ticker"] for r in rows]

    hits = signals.scan_universe(tickers, persist=True)
    if not hits:
        print("no hits")
        return

    # Latest trade_date in this batch
    latest_td = max(h.trade_date for h in hits)
    today_hits = [h for h in hits if h.trade_date == latest_td]
    by_ticker = signals.latest_hits_summary(today_hits)

    print()
    print(f"=== anomaly scan {latest_td} — {len(by_ticker)} tickers triggered ===")
    print()
    # Sort tickers by number of distinct signal types (more signals = stronger)
    ranked = sorted(by_ticker.items(), key=lambda kv: -len(kv[1]))
    for ticker, ths in ranked:
        types = ", ".join(SIGNAL_LABELS.get(h.signal_type, h.signal_type) for h in ths)
        scores = " ".join(
            f"{SIGNAL_LABELS.get(h.signal_type, h.signal_type)}={h.score:.2f}"
            for h in ths
        )
        n = len(ths)
        marker = "★★★" if n >= 3 else ("★★" if n == 2 else "★")
        print(f"  {marker} {ticker:<6} [{types}]  {scores}")

    print()
    print(f"  full hit log: sqlite3 data/invest.db \"SELECT * FROM signals "
          f"WHERE trade_date='{latest_td}' ORDER BY ticker;\"")


if __name__ == "__main__":
    main()
