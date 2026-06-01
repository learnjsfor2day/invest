"""Print upcoming earnings for tickers on company_list.jsonl.

Usage:
    python scripts/upcoming_earnings.py            # next 14 days
    python scripts/upcoming_earnings.py 30         # next 30 days

Reads FMP earnings calendar, intersects with watchlist (us_tradable=true),
prints sorted by date. No DB writes.
"""
from __future__ import annotations
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.config import has_fmp  # noqa: E402
from pipeline.sources import fmp_earnings_calendar  # noqa: E402

POOL = ROOT / "company_list.jsonl"


def main() -> None:
    if not has_fmp():
        print("FMP_API_KEY not set — cannot fetch earnings calendar.")
        print("Set it in .env, then: set -a && source .env && set +a")
        sys.exit(1)

    days = int(sys.argv[1]) if len(sys.argv) > 1 else 14
    today = date.today()
    to = today + timedelta(days=days)

    watch: dict[str, dict] = {}
    with POOL.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("us_tradable") and r.get("ticker"):
                watch[r["ticker"]] = r

    cal = fmp_earnings_calendar(today.isoformat(), to.isoformat())
    hits = [e for e in cal if e.get("symbol") in watch]
    hits.sort(key=lambda e: (e.get("date") or "", e.get("symbol") or ""))

    print(f"Upcoming earnings on watchlist  ({today} → {to}, {days}d)")
    print(f"  watchlist size: {len(watch)} | calendar entries: {len(cal)} | hits: {len(hits)}")
    print()
    print(f"  {'DATE':<12} {'TICKER':<7} {'EPS_EST':>9} {'REV_EST':>14}  TAGS")
    print(f"  {'-'*12} {'-'*7} {'-'*9} {'-'*14}  {'-'*40}")
    for e in hits:
        sym = e.get("symbol", "")
        d = e.get("date", "")
        eps = e.get("epsEstimated")
        rev = e.get("revenueEstimated")
        eps_s = f"{eps:>9.2f}" if isinstance(eps, (int, float)) else " " * 9
        rev_s = f"{rev/1e9:>11.2f}B" if isinstance(rev, (int, float)) else " " * 14
        tags = ",".join(watch[sym].get("tags", [])[:4])
        print(f"  {d:<12} {sym:<7} {eps_s} {rev_s}  {tags}")


if __name__ == "__main__":
    main()
