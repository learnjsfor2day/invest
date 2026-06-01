"""End-to-end orchestration.

Steps per ticker:
  1. Pull latest quarterly fundamentals (FMP if available, else skip).
  2. Pull most recent earnings call transcript (FMP if available).
  3. Run LLM extraction on transcript → quotes + structured signals.
  4. Merge signals into the earnings row, upsert to DB.
  5. Pull stock reaction via yfinance (best effort).
  6. Classify into tier (1-4) using deterministic rules.
  7. Record tier + quotes + run summary.

In addition (cross-ticker):
  - Poll SEC EDGAR 8-K feed for the watchlist; record new alerts; notify.
"""
from __future__ import annotations
from datetime import date, datetime, timedelta
from typing import Optional

from . import db
from .config import has_fmp, has_anthropic
from .extract import extract_from_transcript
from .notify import notify
from .sources import (
    fmp_income_statement, fmp_transcripts, fmp_earnings_calendar,
    list_recent_filings, filings_for_ticker, price_reaction, get_cik,
)
from .tiers import classify, inputs_from_earnings


def _fiscal_period_label(year: int, quarter: int) -> str:
    return f"{year}-Q{quarter}"


def _period_from_fmp_income(item: dict) -> str:
    # FMP income statement: 'period' is "Q1"/"Q2"... 'calendarYear' is year
    y = item.get("calendarYear") or item.get("date", "")[:4]
    q = item.get("period", "").lstrip("Q")
    if y and q:
        return f"{y}-Q{q}"
    return item.get("date", "")[:7] or "unknown"


def _stock_runup_3mo(ticker: str) -> Optional[float]:
    try:
        import yfinance as yf  # type: ignore
    except ImportError:
        return None
    end = datetime.utcnow()
    start = end - timedelta(days=100)
    try:
        h = yf.Ticker(ticker).history(start=start.strftime("%Y-%m-%d"),
                                       end=end.strftime("%Y-%m-%d"),
                                       auto_adjust=False)
    except Exception:
        return None
    if h is None or h.empty or len(h) < 2:
        return None
    closes = h["Close"].tolist()
    return (closes[-1] - closes[0]) / closes[0]


def update_company(ticker: str) -> dict:
    """Run pipeline for one ticker. Returns summary dict."""
    summary = {
        "ticker": ticker, "earnings_added": 0,
        "quotes": 0, "tier": None, "matches": [], "notes": [],
    }

    # 1. Fundamentals (requires FMP)
    fundamentals: list[dict] = []
    if has_fmp():
        try:
            fundamentals = fmp_income_statement(ticker, period="quarter", limit=2)
        except Exception as e:
            summary["notes"].append(f"FMP income failed: {e}")
    else:
        summary["notes"].append("FMP key missing — fundamentals skipped")

    if not fundamentals:
        # Without fundamentals we cannot create an earnings row. Still try alerts.
        return summary

    latest = fundamentals[0]
    period = _period_from_fmp_income(latest)
    report_date = latest.get("date") or latest.get("fillingDate")
    revenue_m = (latest.get("revenue") or 0) / 1e6
    prior = fundamentals[1] if len(fundamentals) > 1 else None
    revenue_yoy = None  # FMP quarterly doesn't directly give YoY — would need prior-year same quarter
    revenue_qoq = None
    if prior and prior.get("revenue"):
        revenue_qoq = (latest["revenue"] - prior["revenue"]) / prior["revenue"]

    earnings_row = {
        "ticker": ticker,
        "fiscal_period": period,
        "report_date": report_date,
        "currency": latest.get("reportedCurrency", "USD"),
        "revenue": revenue_m,
        "revenue_yoy": revenue_yoy,
        "revenue_qoq": revenue_qoq,
        "gross_margin": (latest.get("grossProfitRatio") or None),
        "operating_margin": (latest.get("operatingIncomeRatio") or None),
        "operating_income": (latest.get("operatingIncome") or 0) / 1e6 or None,
        "net_income": (latest.get("netIncome") or 0) / 1e6 or None,
        "eps": latest.get("eps"),
        "cloud_revenue": None, "cloud_revenue_yoy": None,
        "ai_arr": None, "ai_arr_yoy": None,
        "backlog_rpo": None, "backlog_rpo_qoq": None,
        "capex_quarter": None, "capex_full_year_low": None, "capex_full_year_high": None,
        "guidance_text": None,
        "source_url": latest.get("link") or "",
        "transcript_url": "",
        "notes": "",
    }

    # 2 + 3. Transcript + LLM extraction
    capacity_constrained = None
    if has_fmp() and has_anthropic():
        try:
            tr = fmp_transcripts(ticker)  # most recent
            if tr:
                tr_text = tr[0].get("content", "")
                earnings_row["transcript_url"] = tr[0].get("url", "") or ""
                result = extract_from_transcript(tr_text, ticker, period)
                result.merge_into_earnings_row(earnings_row)
                capacity_constrained = result.signals.get("capacity_constrained")
                for q in result.quotes:
                    db.add_quote(ticker, period, q.quote, q.speaker, q.topic,
                                 earnings_row["transcript_url"])
                summary["quotes"] = len(result.quotes)
        except Exception as e:
            summary["notes"].append(f"transcript/LLM failed: {e}")
    else:
        if not has_fmp():
            summary["notes"].append("transcripts skipped (FMP key missing)")
        if not has_anthropic():
            summary["notes"].append("LLM extraction skipped (Anthropic key missing)")

    # 4. Upsert earnings
    inserted = db.upsert_earnings(earnings_row)
    summary["earnings_added"] = inserted

    # 5. Stock reaction
    if report_date:
        try:
            pr = price_reaction(ticker, report_date)
            if pr and pr.get("next_day_pct") is not None:
                summary["notes"].append(
                    f"price t+1: {pr['next_day_pct']*100:+.1f}%"
                    + (f", t+3: {pr.get('t_plus_3_pct',0)*100:+.1f}%"
                       if pr.get("t_plus_3_pct") is not None else "")
                )
        except Exception as e:
            summary["notes"].append(f"price reaction failed: {e}")

    # 6. Classify tier
    runup = _stock_runup_3mo(ticker)
    prior_db_row = db.previous_earnings(ticker, period)
    inputs = inputs_from_earnings(
        earnings_row,
        prior_row=dict(prior_db_row) if prior_db_row else None,
        capacity_constrained=capacity_constrained,
        stock_runup_3mo=runup,
    )
    res = classify(inputs)
    db.record_tier(ticker, period, res.tier, res.rule_matches, res.reason)
    summary["tier"] = res.tier
    summary["matches"] = res.rule_matches

    return summary


def poll_8k_alerts(watchlist_tickers: list[str]) -> int:
    """Pull SEC EDGAR 8-K filings for tickers in the watchlist. Free, no key.

    Strategy: per-ticker `filings_for_ticker(ticker, '8-K', limit=5)` — the
    submissions endpoint is more reliable than the global atom feed for
    company-specific monitoring. Records new ones to alerts table.
    """
    new_count = 0
    for ticker in watchlist_tickers:
        cik = get_cik(ticker)
        if not cik:
            continue
        try:
            filings = filings_for_ticker(ticker, form="8-K", limit=5)
        except Exception:
            continue
        for f in filings:
            inserted = db.record_alert(
                ticker=ticker, cik=cik, form_type=f.form_type,
                filing_date=f.filing_date, accession=f.accession,
                title=f.title, url=f.url,
            )
            if inserted:
                new_count += 1
                notify(
                    f"[8-K] {ticker} {f.filing_date}",
                    f"{f.title or '(no title)'}\n{f.url}",
                )
    return new_count


def run_pipeline(tickers: list[str]) -> dict:
    """Orchestrate everything for a list of tickers."""
    db.init_db()
    run_id = db.start_run()
    summaries: list[dict] = []
    earnings_added = 0
    quotes_extracted = 0
    for t in tickers:
        try:
            s = update_company(t)
        except Exception as e:
            s = {"ticker": t, "earnings_added": 0, "quotes": 0,
                 "tier": None, "matches": [], "notes": [f"FATAL: {e}"]}
        summaries.append(s)
        earnings_added += s.get("earnings_added", 0)
        quotes_extracted += s.get("quotes", 0)

    alerts = 0
    try:
        alerts = poll_8k_alerts(tickers)
    except Exception as e:
        summaries.append({"ticker": "_alerts", "notes": [f"alerts failed: {e}"]})

    db.finish_run(
        run_id, tickers=tickers,
        earnings_added=earnings_added, alerts_seen=alerts,
        quotes_extracted=quotes_extracted,
        notes=f"summaries: {len(summaries)}",
    )

    # human summary
    lines = [f"Pipeline run {run_id} — {len(tickers)} tickers"]
    for s in summaries:
        ticker = s["ticker"]
        tier = s.get("tier")
        notes = "; ".join(s.get("notes", []))
        lines.append(
            f"  {ticker:<6} tier={tier}  earnings_added={s.get('earnings_added',0)}"
            f"  quotes={s.get('quotes',0)}  notes={notes}"
        )
    if alerts:
        lines.append(f"New 8-K alerts: {alerts}")
    notify("Pipeline run complete", "\n".join(lines))

    return {
        "run_id": run_id,
        "summaries": summaries,
        "earnings_added": earnings_added,
        "alerts_seen": alerts,
        "quotes_extracted": quotes_extracted,
    }


if __name__ == "__main__":
    import sys
    tickers = sys.argv[1:] or ["GOOGL", "MSFT"]
    run_pipeline(tickers)
