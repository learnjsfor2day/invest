"""Data sources.

- SEC EDGAR (free): 8-K and submissions. Just needs a User-Agent.
- FMP (paid, env-gated): earnings calendar, transcripts, fundamentals.
- yfinance (free): price reaction.

All modules are designed to no-op gracefully when their dependency / key is
missing — pipeline can run end-to-end with zero keys (limited functionality).
"""
from __future__ import annotations
import json
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable, Optional

from .config import FMP_API_KEY, SEC_USER_AGENT, has_fmp


# =====================================================================
# SEC EDGAR — free, no key needed (just User-Agent)
# =====================================================================

EDGAR_RECENT_FILINGS = (
    "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type={form}&output=atom"
)
EDGAR_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik10}.json"
EDGAR_TICKER_MAP = "https://www.sec.gov/files/company_tickers.json"

# Cached ticker→CIK map (built lazily, cached in memory per process)
_TICKER_CIK_CACHE: dict[str, str] = {}


def _http_get(url: str, *, accept_json: bool = False) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": SEC_USER_AGENT,
            "Accept": "application/json" if accept_json else "*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read()


def load_ticker_cik_map(force: bool = False) -> dict[str, str]:
    """Load SEC's official ticker → CIK map. Cached after first call."""
    global _TICKER_CIK_CACHE
    if _TICKER_CIK_CACHE and not force:
        return _TICKER_CIK_CACHE
    raw = _http_get(EDGAR_TICKER_MAP, accept_json=True)
    data = json.loads(raw)
    out: dict[str, str] = {}
    for entry in data.values():
        ticker = entry["ticker"].upper()
        cik = str(entry["cik_str"]).zfill(10)
        out[ticker] = cik
    _TICKER_CIK_CACHE = out
    return out


def get_cik(ticker: str) -> Optional[str]:
    try:
        return load_ticker_cik_map().get(ticker.upper())
    except Exception:
        return None


@dataclass
class Filing:
    ticker: Optional[str]
    cik: Optional[str]
    form_type: str
    filing_date: str  # ISO
    accession: str
    title: str
    url: str


def list_recent_filings(form: str = "8-K", since_days: int = 7) -> list[Filing]:
    """List recent filings of a given form across all issuers.

    SEC's atom feed returns the latest ~40 filings for that form. Useful for
    near-realtime 8-K monitoring. Filter to your watchlist downstream.
    """
    url = EDGAR_RECENT_FILINGS.format(form=urllib.parse.quote(form))
    raw = _http_get(url)
    cutoff = datetime.utcnow() - timedelta(days=since_days)
    out: list[Filing] = []
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(raw)
    for entry in root.findall("a:entry", ns):
        title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip()
        link_el = entry.find("a:link", ns)
        url_ = link_el.get("href") if link_el is not None else ""
        updated = entry.findtext("a:updated", default="", namespaces=ns)
        # accession # is in the URL or the id
        acc = ""
        id_text = entry.findtext("a:id", default="", namespaces=ns)
        if "accession-number=" in id_text:
            acc = id_text.split("accession-number=")[-1]
        cik = ""
        if "CIK=" in url_:
            cik = url_.split("CIK=")[-1].split("&")[0]
        try:
            dt = datetime.fromisoformat(updated.replace("Z", "+00:00")) if updated else None
        except ValueError:
            dt = None
        if dt and dt.replace(tzinfo=None) < cutoff:
            continue
        out.append(Filing(
            ticker=None, cik=cik, form_type=form,
            filing_date=updated, accession=acc, title=title, url=url_,
        ))
    return out


def filings_for_ticker(ticker: str, form: str = "8-K", limit: int = 10) -> list[Filing]:
    """Per-issuer filings via data.sec.gov submissions JSON."""
    cik = get_cik(ticker)
    if not cik:
        return []
    url = EDGAR_SUBMISSIONS.format(cik10=cik)
    raw = _http_get(url, accept_json=True)
    data = json.loads(raw)
    rec = data.get("filings", {}).get("recent", {})
    forms = rec.get("form", [])
    accs = rec.get("accessionNumber", [])
    dates = rec.get("filingDate", [])
    titles = rec.get("primaryDocDescription", [])
    primaries = rec.get("primaryDocument", [])
    out: list[Filing] = []
    for f, a, d, t, p in zip(forms, accs, dates, titles, primaries):
        if f != form:
            continue
        acc_clean = a.replace("-", "")
        url_ = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{p}"
        out.append(Filing(
            ticker=ticker.upper(), cik=cik, form_type=f,
            filing_date=d, accession=a, title=t or "", url=url_,
        ))
        if len(out) >= limit:
            break
    return out


# =====================================================================
# FMP — paid, env-gated. Modules return None / [] when no key.
# =====================================================================

# FMP migrated v3 → /stable/ on 2025-08-31; v3 returns HTTP 403 "Legacy Endpoint".
FMP_BASE = "https://financialmodelingprep.com/stable"


def _fmp_get(path: str, params: dict[str, Any] | None = None) -> Any:
    if not has_fmp():
        return None
    p = dict(params or {})
    p["apikey"] = FMP_API_KEY
    url = f"{FMP_BASE}{path}?{urllib.parse.urlencode(p)}"
    try:
        raw = _http_get(url, accept_json=True)
    except urllib.error.HTTPError as e:
        # 402 = endpoint not on subscription tier; 403 = bad/legacy. Treat as no data.
        if e.code in (402, 403):
            return None
        raise
    return json.loads(raw)


def fmp_earnings_calendar(from_date: str, to_date: str) -> list[dict]:
    """Calendar of upcoming earnings. from_date / to_date as YYYY-MM-DD."""
    if not has_fmp():
        return []
    data = _fmp_get("/earnings-calendar", {"from": from_date, "to": to_date})
    return data or []


def fmp_income_statement(ticker: str, period: str = "quarter", limit: int = 4) -> list[dict]:
    if not has_fmp():
        return []
    data = _fmp_get("/income-statement",
                    {"symbol": ticker, "period": period, "limit": limit})
    return data or []


def fmp_cash_flow(ticker: str, period: str = "quarter", limit: int = 4) -> list[dict]:
    if not has_fmp():
        return []
    data = _fmp_get("/cash-flow-statement",
                    {"symbol": ticker, "period": period, "limit": limit})
    return data or []


def fmp_transcripts(ticker: str, year: Optional[int] = None,
                    quarter: Optional[int] = None) -> list[dict]:
    """Earnings call transcripts. Returns list of {date, content, ...}.
    NOTE: requires a paid FMP tier — free key gets HTTP 402 → []."""
    if not has_fmp():
        return []
    params: dict[str, Any] = {"symbol": ticker}
    if year:
        params["year"] = year
    if quarter:
        params["quarter"] = quarter
    data = _fmp_get("/earning-call-transcript", params)
    return data or []


# =====================================================================
# yfinance — free, optional dependency
# =====================================================================

def price_reaction(ticker: str, around_date: str) -> Optional[dict]:
    """Return %change from close on `around_date` to next session close, plus
    next-3-day cumulative move. `around_date` = 'YYYY-MM-DD' (the report date,
    expected after-market close on US schedule).

    Returns None if yfinance isn't installed or data unavailable.
    """
    try:
        import yfinance as yf  # type: ignore
    except ImportError:
        return None
    try:
        d = datetime.fromisoformat(around_date)
    except ValueError:
        return None
    start = (d - timedelta(days=2)).strftime("%Y-%m-%d")
    end = (d + timedelta(days=8)).strftime("%Y-%m-%d")
    try:
        hist = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=False)
    except Exception:
        return None
    if hist is None or hist.empty:
        return None
    closes = hist["Close"].tolist()
    dates = [d.strftime("%Y-%m-%d") for d in hist.index.to_pydatetime()]
    if around_date not in dates:
        return {"note": f"no trading on {around_date}; nearest session: {dates[0] if dates else 'n/a'}"}
    i = dates.index(around_date)
    out: dict[str, Any] = {"report_close": closes[i], "report_date": around_date}
    if i + 1 < len(closes):
        out["next_day_pct"] = (closes[i + 1] - closes[i]) / closes[i]
        out["next_day_date"] = dates[i + 1]
    if i + 3 < len(closes):
        out["t_plus_3_pct"] = (closes[i + 3] - closes[i]) / closes[i]
    return out
