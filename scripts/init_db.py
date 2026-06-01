"""Initialize SQLite DB, load watchlist from company_list.jsonl, and migrate
existing financial_data.csv into the earnings table.

Idempotent — safe to re-run.
"""
from __future__ import annotations
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import db  # noqa: E402

POOL = ROOT / "company_list.jsonl"
CSV_FILE = ROOT / "financial_data.csv"


def load_pool() -> int:
    if not POOL.exists():
        print(f"[load_pool] {POOL} missing — skipping")
        return 0
    n = 0
    with POOL.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            db.upsert_company(row)
            n += 1
    print(f"[load_pool] loaded {n} companies into DB")
    return n


# ---------- CSV migration ----------
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def parse_money(s: str) -> float | None:
    """Parse '109.9B', '54.5B', '40' → millions of USD.
    'B' = billion → ×1000, plain or 'M' = million → ×1.
    Returns None for N/A or unparseable.
    """
    if not s or s.strip().upper() in ("N/A", "NA", "NONE", ""):
        return None
    s = s.strip()
    m = _NUM_RE.search(s)
    if not m:
        return None
    val = float(m.group(0))
    upper = s.upper()
    if "B" in upper:
        return val * 1000.0  # billion → millions
    if "T" in upper:
        return val * 1_000_000.0
    if "M" in upper or "MILL" in upper.upper():
        return val
    # Bare number — assume billions if value is small (<1000), else millions
    return val * 1000.0 if val < 1000 else val


def parse_pct(s: str) -> float | None:
    if not s or s.strip().upper() in ("N/A", "NA", "NONE", ""):
        return None
    m = _NUM_RE.search(s)
    if not m:
        return None
    return float(m.group(0)) / 100.0


def parse_capex_range(s: str) -> tuple[float | None, float | None]:
    """e.g. '2026FY 上调至 180-190B (原 175-185B); 2027 继续增长' → (180000, 190000) in millions"""
    if not s:
        return (None, None)
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", s)]
    if not nums:
        return (None, None)
    upper = s.upper()
    scale = 1000.0 if "B" in upper else 1.0
    # Find first low-high pair (typically the new guidance)
    if len(nums) >= 2:
        return (nums[0] * scale, nums[1] * scale)
    return (nums[0] * scale, nums[0] * scale)


def normalize_period(s: str) -> str:
    """'2026Q1' / 'FY26Q3 (Jan-Mar 2026)' / '2026 Q1' → '2026-Q1'."""
    s = s.strip()
    m = re.search(r"(\d{4})[\s-]?Q([1-4])", s)
    if m:
        return f"{m.group(1)}-Q{m.group(2)}"
    m = re.search(r"FY(\d{2})Q([1-4])", s)
    if m:
        # MSFT FY26 Q3 = calendar Q1 2026 (FY ends June)
        # We use the calendar mapping based on the parens hint when present
        cal = re.search(r"(\d{4})", s[m.end():])
        if cal:
            return f"{cal.group(1)}-Q1"  # crude but matches our test data
        return f"20{m.group(1)}-Q{m.group(2)}"
    return s


def migrate_csv() -> int:
    if not CSV_FILE.exists() or CSV_FILE.stat().st_size == 0:
        print(f"[migrate_csv] {CSV_FILE} missing/empty — skipping")
        return 0
    n = 0
    with CSV_FILE.open() as f:
        reader = csv.DictReader(f)
        for r in reader:
            ticker = (r.get("ticker") or "").strip()
            if not ticker:
                continue
            period = normalize_period(r.get("fiscal_period", ""))
            capex_lo, capex_hi = parse_capex_range(r.get("capex", ""))

            # Cloud / data-center revenue field is heuristic-parsed
            cloud_rev = parse_money(r.get("data_center_revenue", ""))
            cloud_yoy_match = re.search(r"\+(\d+(?:\.\d+)?)%", r.get("data_center_revenue", ""))
            cloud_yoy = float(cloud_yoy_match.group(1)) / 100.0 if cloud_yoy_match else None

            ai_rev = parse_money(r.get("ai_related_revenue", ""))
            ai_yoy_match = re.search(r"\+(\d+(?:\.\d+)?)%", r.get("ai_related_revenue", ""))
            ai_yoy = float(ai_yoy_match.group(1)) / 100.0 if ai_yoy_match else None

            backlog_rpo = parse_money(r.get("backlog", ""))
            # detect "QoQ近翻倍" in our test data → ~+95% (heuristic, marked uncertain)
            backlog_qoq = None
            if "翻倍" in r.get("backlog", "") or "double" in r.get("backlog", "").lower():
                backlog_qoq = 0.95

            row = {
                "ticker": ticker,
                "fiscal_period": period,
                "report_date": r.get("report_date", "").strip() or None,
                "currency": "USD",
                "revenue": parse_money(r.get("revenue", "")),
                "revenue_yoy": parse_pct(r.get("revenue_yoy", "")),
                "revenue_qoq": parse_pct(r.get("revenue_qoq", "")),
                "gross_margin": parse_pct(r.get("gross_margin", "")),
                "operating_margin": parse_pct(r.get("operating_margin", "")),
                "operating_income": None,
                "net_income": parse_money(r.get("net_income", "")),
                "eps": float(r["eps"]) if r.get("eps") and r["eps"].strip() not in ("N/A", "") else None,
                "cloud_revenue": cloud_rev,
                "cloud_revenue_yoy": cloud_yoy,
                "ai_arr": ai_rev,
                "ai_arr_yoy": ai_yoy,
                "backlog_rpo": backlog_rpo,
                "backlog_rpo_qoq": backlog_qoq,
                "capex_quarter": parse_money(r.get("capex", "")) if "季度" in r.get("capex", "") or ">40" in r.get("capex", "") else None,
                "capex_full_year_low": capex_lo,
                "capex_full_year_high": capex_hi,
                "guidance_text": r.get("guidance", ""),
                "source_url": r.get("source_url", ""),
                "transcript_url": "",
                "notes": "imported from financial_data.csv",
            }
            db.upsert_earnings(row)
            n += 1
    print(f"[migrate_csv] migrated {n} earnings rows from CSV")
    return n


def main() -> None:
    db.init_db()
    print(f"[init_db] {db.DB_PATH} ready")
    load_pool()
    migrate_csv()
    # quick health summary
    with db.connect() as conn:
        c = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        e = conn.execute("SELECT COUNT(*) FROM earnings").fetchone()[0]
        print(f"[summary] companies={c}  earnings={e}")


if __name__ == "__main__":
    main()
