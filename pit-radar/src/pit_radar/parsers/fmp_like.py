from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pit_radar.parsers.base import (
    AnalystRecord,
    DailyBarRecord,
    EarningsRecord,
    EstimateRecord,
    FinancialFactRecord,
    MacroEventRecord,
    MetricRecord,
    NewsRecord,
    ParsedPayload,
    SecFilingRecord,
    SecurityRecord,
    SourceDocumentRecord,
    TranscriptRecord,
)


def parse_fmp_like_payload(dataset_code: str, data: dict[str, Any], fetched_at: datetime) -> ParsedPayload:
    if dataset_code == "macro_events":
        return ParsedPayload(macro_events=_parse_macro_events(data, fetched_at))

    symbol = str(data.get("symbol") or data.get("ticker") or "").upper()
    profile = data.get("profile") or {}
    security = SecurityRecord(
        symbol=symbol,
        company_name=_text(_pick(profile, "companyName", "company_name", "name")),
        exchange=_pick(profile, "exchangeShortName", "exchange", "exchangeName"),
        cik=_clean_cik(_pick(profile, "cik", "CIK")),
        cusip=_pick(profile, "cusip", "CUSIP"),
        isin=_pick(profile, "isin", "ISIN"),
        sector=_pick(profile, "sector"),
        industry=_pick(profile, "industry"),
        currency=_pick(profile, "currency") or "USD",
        country=_pick(profile, "country") or "US",
    )
    parsed = ParsedPayload(securities=[security])

    if dataset_code == "estimates":
        parsed.estimates.extend(_parse_estimates(symbol, data, fetched_at, security.currency or "USD"))
        analyst = _parse_analyst(symbol, data, fetched_at)
        if analyst:
            parsed.analysts.append(analyst)
        parsed.metrics.extend(_parse_metrics(symbol, data, fetched_at, security.currency or "USD"))
    elif dataset_code == "daily_bars":
        parsed.daily_bars.extend(_parse_daily_bars(symbol, data))
        parsed.metrics.extend(_parse_profile_metrics(symbol, profile, fetched_at, security.currency or "USD"))
    elif dataset_code == "earnings":
        parsed.earnings.extend(_parse_earnings(symbol, data, fetched_at))
        parsed.metrics.extend(_parse_profile_metrics(symbol, profile, fetched_at, security.currency or "USD"))
    elif dataset_code == "news":
        parsed.news.extend(_parse_news(symbol, data, fetched_at))
        parsed.source_documents.extend(_parse_news_documents(symbol, data, fetched_at))
    elif dataset_code == "financials":
        parsed.financial_facts.extend(_parse_financial_facts(symbol, data, fetched_at, security.currency or "USD"))
        parsed.metrics.extend(_parse_profile_metrics(symbol, profile, fetched_at, security.currency or "USD"))
    elif dataset_code == "sec_filings":
        parsed.sec_filings.extend(_parse_sec_filings(symbol, data, fetched_at))
        parsed.source_documents.extend(_parse_sec_filing_documents(symbol, data, fetched_at))
    elif dataset_code == "transcripts":
        parsed.transcripts.extend(_parse_transcripts(symbol, data, fetched_at))
        parsed.source_documents.extend(_parse_transcript_documents(symbol, data, fetched_at))
    return parsed


def _parse_estimates(symbol: str, data: dict[str, Any], fetched_at: datetime, currency: str) -> list[EstimateRecord]:
    records: list[EstimateRecord] = []
    for row in data.get("estimates") or []:
        period_end = _date(_pick(row, "date", "fiscalDateEnding", "fiscal_period_end"))
        if not period_end:
            continue
        period = str(_pick(row, "period", "periodType", "period_type") or "annual").lower()
        period_type = "quarter" if period in {"quarter", "q", "quarterly"} else "fiscal_year"
        quality = _quality_high_low(
            eps_high=_decimal(_pick(row, "epsHigh", "estimatedEpsHigh", "eps_high")),
            eps_low=_decimal(_pick(row, "epsLow", "estimatedEpsLow", "eps_low")),
            revenue_high=_decimal(_pick(row, "revenueHigh", "estimatedRevenueHigh", "revenue_high")),
            revenue_low=_decimal(_pick(row, "revenueLow", "estimatedRevenueLow", "revenue_low")),
        )
        records.append(
            EstimateRecord(
                symbol=symbol,
                fiscal_period_end=period_end,
                period_type=period_type,
                snapshot_at=fetched_at,
                eps_mean=_decimal(_pick(row, "epsAvg", "estimatedEpsAvg", "estimatedEpsAverage", "eps_mean")),
                eps_high=_decimal(_pick(row, "epsHigh", "estimatedEpsHigh", "eps_high")),
                eps_low=_decimal(_pick(row, "epsLow", "estimatedEpsLow", "eps_low")),
                analyst_count_eps=_int(
                    _pick(row, "numAnalystsEps", "numberAnalystEstimatedEps", "numberAnalystsEstimatedEps", "analyst_count_eps")
                ),
                revenue_mean=_decimal(_pick(row, "revenueAvg", "estimatedRevenueAvg", "estimatedRevenueAverage", "revenue_mean")),
                revenue_high=_decimal(_pick(row, "revenueHigh", "estimatedRevenueHigh", "revenue_high")),
                revenue_low=_decimal(_pick(row, "revenueLow", "estimatedRevenueLow", "revenue_low")),
                analyst_count_revenue=_int(
                    _pick(row, "numAnalystsRevenue", "numberAnalystsEstimatedRevenue", "numberAnalystEstimatedRevenue", "analyst_count_revenue")
                ),
                currency=currency,
                quality_flags=quality,
            )
        )
    return records


def _parse_analyst(symbol: str, data: dict[str, Any], fetched_at: datetime) -> AnalystRecord | None:
    target = data.get("price_target") or {}
    grades = data.get("grades_consensus") or {}
    if not target and not grades:
        return None
    return AnalystRecord(
        symbol=symbol,
        snapshot_at=fetched_at,
        target_mean=_decimal(_pick(target, "targetConsensus", "targetMean", "target_mean", "targetPrice")),
        target_high=_decimal(_pick(target, "targetHigh", "target_high", "high")),
        target_low=_decimal(_pick(target, "targetLow", "target_low", "low")),
        strong_buy_count=_int(_pick(grades, "strongBuy", "strong_buy", "strong_buy_count")),
        buy_count=_int(_pick(grades, "buy", "buy_count")),
        hold_count=_int(_pick(grades, "hold", "hold_count")),
        sell_count=_int(_pick(grades, "sell", "sell_count")),
        strong_sell_count=_int(_pick(grades, "strongSell", "strong_sell", "strong_sell_count")),
    )


def _parse_earnings(symbol: str, data: dict[str, Any], fetched_at: datetime) -> list[EarningsRecord]:
    output: list[EarningsRecord] = []
    for row in data.get("earnings") or []:
        explicit_fiscal_end = _date(_pick(row, "fiscalDateEnding", "fiscal_period_end", "periodEnd"))
        fiscal_end = explicit_fiscal_end or _date(_pick(row, "date"))
        if not fiscal_end:
            continue
        quality: dict[str, Any] = {}
        if explicit_fiscal_end is None:
            quality["fiscal_period_end_missing_using_report_date"] = True
        last_updated = _pick(row, "lastUpdated", "updatedAt")
        if last_updated:
            quality["fmp_last_updated"] = str(last_updated)
        output.append(
            EarningsRecord(
                symbol=symbol,
                fiscal_period_end=fiscal_end,
                expected_report_date=_date(_pick(row, "date", "expectedReportDate")),
                expected_report_session=_session(_pick(row, "time", "session")),
                estimated_eps=_decimal(_pick(row, "epsEstimated", "estimatedEps", "estimated_eps")),
                estimated_revenue=_decimal(_pick(row, "revenueEstimated", "estimatedRevenue", "estimated_revenue")),
                actual_eps=_decimal(_pick(row, "epsActual", "actualEps", "actual_eps")),
                actual_revenue=_decimal(_pick(row, "revenueActual", "actualRevenue", "actual_revenue")),
                eps_surprise=_decimal(_pick(row, "epsSurprise", "surprise", "eps_surprise")),
                eps_surprise_percent=_decimal(_pick(row, "epsSurprisePercent", "surprisePercentage", "eps_surprise_percent")),
                revenue_surprise=_decimal(_pick(row, "revenueSurprise", "revenue_surprise")),
                revenue_surprise_percent=_decimal(_pick(row, "revenueSurprisePercent", "revenue_surprise_percent")),
                snapshot_at=fetched_at,
                quality_flags=quality,
            )
        )
    return output


def _parse_daily_bars(symbol: str, data: dict[str, Any]) -> list[DailyBarRecord]:
    output: list[DailyBarRecord] = []
    for row in data.get("historical") or []:
        trade_date = _date(_pick(row, "date"))
        if not trade_date:
            continue
        high = _decimal(_pick(row, "high"))
        low = _decimal(_pick(row, "low"))
        flags: dict[str, Any] = {}
        if high is not None and low is not None and high < low:
            flags["high_below_low"] = True
        output.append(
            DailyBarRecord(
                symbol=symbol,
                trade_date=trade_date,
                open=_decimal(_pick(row, "open")),
                high=high,
                low=low,
                close=_decimal(_pick(row, "close")),
                adjusted_close=_decimal(_pick(row, "adjClose", "adjustedClose", "adjusted_close")),
                volume=_decimal(_pick(row, "volume")),
                quality_flags=flags,
            )
        )
    return output


def _parse_news(symbol: str, data: dict[str, Any], fetched_at: datetime) -> list[NewsRecord]:
    output: list[NewsRecord] = []
    for row in _dict_rows(data.get("news")):
        if not isinstance(row, dict):
            continue
        title = _text(_pick(row, "title", "headline"))
        url = _text(_pick(row, "url", "link"))
        published_at = _datetime(_pick(row, "publishedDate", "published_at", "date", "published_at_utc"))
        if not title and not url:
            continue
        quality: dict[str, Any] = {}
        if published_at is None:
            quality["published_at_missing"] = True
        output.append(
            NewsRecord(
                symbol=symbol,
                news_type=str(_pick(row, "_news_type", "newsType", "type") or "stock_news"),
                published_at=published_at,
                title=title,
                url=url,
                publisher=_text(_pick(row, "site", "publisher", "source")),
                author=_text(_pick(row, "author")),
                summary=_text(_pick(row, "text", "summary", "content")),
                image_url=_text(_pick(row, "image", "imageUrl", "thumbnail")),
                sentiment_label=_text(_pick(row, "sentiment", "sentimentLabel")),
                sentiment_score=_decimal(_pick(row, "sentimentScore", "score")),
                source_published_at=published_at or fetched_at,
                quality_flags=quality,
            )
        )
    return output


def _parse_news_documents(symbol: str, data: dict[str, Any], fetched_at: datetime) -> list[SourceDocumentRecord]:
    output: list[SourceDocumentRecord] = []
    for row in _dict_rows(data.get("news")):
        title = _text(_pick(row, "title", "headline"))
        url = _text(_pick(row, "url", "link"))
        published_at = _datetime(_pick(row, "publishedDate", "published_at", "date", "published_at_utc"))
        content = _text(_pick(row, "text", "summary", "content"))
        news_type = str(_pick(row, "_news_type", "newsType", "type") or "stock_news")
        document_type = "press_release" if news_type == "press_release" else "stock_news"
        key = url or _compact_key(document_type, published_at.isoformat() if published_at else None, title)
        if not key:
            continue
        quality: dict[str, Any] = {}
        if not content:
            quality["content_text_missing_link_only"] = True
        output.append(
            SourceDocumentRecord(
                symbol=symbol,
                document_type=document_type,
                document_key=key,
                title=title,
                source_url=url,
                source_event_at=published_at,
                source_published_at=published_at or fetched_at,
                content_text=content,
                metadata_json={"news_type": news_type, "publisher": _text(_pick(row, "site", "publisher", "source"))},
                quality_flags=quality,
            )
        )
    return output


def _parse_financial_facts(symbol: str, data: dict[str, Any], fetched_at: datetime, currency: str) -> list[FinancialFactRecord]:
    output: list[FinancialFactRecord] = []
    financials = data.get("financials") or {}
    if not isinstance(financials, dict):
        return output
    for dataset_code, rows in financials.items():
        for row in _dict_rows(rows):
            period_raw = _pick(row, "period", "periodType")
            period_type = _financial_period_type(period_raw)
            period_end = _date(_pick(row, "date", "fiscalDateEnding", "fiscal_period_end", "periodEnd"))
            accepted_at = _datetime(_pick(row, "acceptedDate", "accepted_at", "acceptedDateTime"))
            filing_date = _date(_pick(row, "filingDate", "fillingDate", "filedDate"))
            quality: dict[str, Any] = {}
            if period_end is None:
                quality["fiscal_period_end_missing"] = True
            output.append(
                FinancialFactRecord(
                    symbol=symbol,
                    dataset_code=str(dataset_code),
                    period_type=period_type,
                    fiscal_period_end=period_end,
                    fiscal_year=_int(_pick(row, "calendarYear", "calendar_year", "fiscalYear", "year")),
                    fiscal_period=_text(period_raw),
                    reported_currency=_text(_pick(row, "reportedCurrency", "currency")) or currency,
                    filing_date=filing_date,
                    accepted_at=accepted_at,
                    source_published_at=accepted_at or (_datetime(filing_date) if filing_date else None) or fetched_at,
                    value_json=_financial_value_json(row),
                    quality_flags=quality,
                )
            )
    return output


FINANCIAL_VALUE_KEYS = {
    "symbol",
    "date",
    "period",
    "calendarYear",
    "reportedCurrency",
    "filingDate",
    "fillingDate",
    "acceptedDate",
    "link",
    "finalLink",
    "revenue",
    "costOfRevenue",
    "grossProfit",
    "grossProfitRatio",
    "researchAndDevelopmentExpenses",
    "sellingGeneralAndAdministrativeExpenses",
    "operatingExpenses",
    "operatingIncome",
    "operatingIncomeRatio",
    "ebitda",
    "ebitdaratio",
    "interestExpense",
    "incomeBeforeTax",
    "incomeTaxExpense",
    "netIncome",
    "netIncomeRatio",
    "eps",
    "epsdiluted",
    "epsDiluted",
    "weightedAverageShsOut",
    "weightedAverageShsOutDil",
    "cashAndCashEquivalents",
    "shortTermInvestments",
    "cashAndShortTermInvestments",
    "netReceivables",
    "inventory",
    "totalCurrentAssets",
    "propertyPlantEquipmentNet",
    "goodwill",
    "intangibleAssets",
    "longTermInvestments",
    "totalAssets",
    "accountPayables",
    "shortTermDebt",
    "taxPayables",
    "totalCurrentLiabilities",
    "longTermDebt",
    "totalDebt",
    "deferredRevenueNonCurrent",
    "totalLiabilities",
    "totalStockholdersEquity",
    "retainedEarnings",
    "totalInvestments",
    "netCashProvidedByOperatingActivities",
    "netCashUsedForInvestingActivites",
    "netCashUsedProvidedByFinancingActivities",
    "capitalExpenditure",
    "freeCashFlow",
    "operatingCashFlow",
    "priceEarningsRatio",
    "peRatio",
    "priceToEarningsRatio",
    "priceToEarningsGrowthRatio",
    "forwardPriceToEarningsGrowthRatio",
    "priceToSalesRatio",
    "priceToBookRatio",
    "priceToFreeCashFlowsRatio",
    "debtEquityRatio",
    "debtToEquity",
    "currentRatio",
    "quickRatio",
    "returnOnAssets",
    "returnOnEquity",
    "returnOnCapitalEmployed",
    "grossProfitMargin",
    "operatingProfitMargin",
    "netProfitMargin",
    "marketCap",
    "enterpriseValue",
    "evToSales",
    "evToOperatingCashFlow",
    "evToFreeCashFlow",
    "evToEbitda",
    "revenuePerShare",
    "netIncomePerShare",
    "operatingCashFlowPerShare",
    "freeCashFlowPerShare",
    "bookValuePerShare",
    "revenueGrowth",
    "grossProfitGrowth",
    "operatingIncomeGrowth",
    "netIncomeGrowth",
    "epsgrowth",
    "epsGrowth",
    "epsdilutedGrowth",
    "freeCashFlowGrowth",
    "operatingCashFlowGrowth",
    "altmanZScore",
    "piotroskiScore",
    "workingCapital",
}


def _financial_value_json(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key in FINANCIAL_VALUE_KEYS and value not in (None, "")}


def _parse_sec_filings(symbol: str, data: dict[str, Any], fetched_at: datetime) -> list[SecFilingRecord]:
    output: list[SecFilingRecord] = []
    for row in _dict_rows(data.get("sec_filings")):
        row_symbol = str(_pick(row, "symbol") or symbol).upper()
        if row_symbol != symbol:
            continue
        accepted_at = _datetime(_pick(row, "acceptedDate", "accepted_at", "acceptedDateTime"))
        filing_date = _date(_pick(row, "filingDate", "fillingDate", "filedDate", "date"))
        quality: dict[str, Any] = {}
        if accepted_at is None:
            quality["accepted_at_missing"] = True
        output.append(
            SecFilingRecord(
                symbol=symbol,
                form_type=_text(_pick(row, "formType", "form_type", "type")),
                filing_date=filing_date,
                accepted_at=accepted_at,
                cik=_clean_cik(_pick(row, "cik", "CIK")),
                filing_url=_text(_pick(row, "link", "filingUrl", "filing_url")),
                final_url=_text(_pick(row, "finalLink", "finalUrl", "final_url")),
                has_financials=_bool(_pick(row, "hasFinancials", "has_financials")),
                source_published_at=accepted_at or (_datetime(filing_date) if filing_date else None) or fetched_at,
                value_json=dict(row),
                quality_flags=quality,
            )
        )
    return output


def _parse_sec_filing_documents(symbol: str, data: dict[str, Any], fetched_at: datetime) -> list[SourceDocumentRecord]:
    output: list[SourceDocumentRecord] = []
    for row in _dict_rows(data.get("sec_filings")):
        row_symbol = str(_pick(row, "symbol") or symbol).upper()
        if row_symbol != symbol:
            continue
        accepted_at = _datetime(_pick(row, "acceptedDate", "accepted_at", "acceptedDateTime"))
        filing_date = _date(_pick(row, "filingDate", "fillingDate", "filedDate", "date"))
        form_type = _text(_pick(row, "formType", "form_type", "type"))
        final_url = _text(_pick(row, "finalLink", "finalUrl", "final_url"))
        filing_url = _text(_pick(row, "link", "filingUrl", "filing_url"))
        source_url = final_url or filing_url
        key = source_url or _compact_key("sec_filing", form_type, accepted_at.isoformat() if accepted_at else None, str(filing_date) if filing_date else None)
        if not key:
            continue
        output.append(
            SourceDocumentRecord(
                symbol=symbol,
                document_type="sec_filing",
                document_key=key,
                title=" ".join(item for item in [form_type, str(filing_date) if filing_date else None] if item),
                source_url=source_url,
                source_event_at=accepted_at or (_datetime(filing_date) if filing_date else None),
                source_published_at=accepted_at or (_datetime(filing_date) if filing_date else None) or fetched_at,
                content_text=None,
                content_type=None,
                metadata_json={
                    "form_type": form_type,
                    "cik": _clean_cik(_pick(row, "cik", "CIK")),
                    "filing_url": filing_url,
                    "final_url": final_url,
                    "has_financials": _bool(_pick(row, "hasFinancials", "has_financials")),
                },
                quality_flags={"link_only": True},
            )
        )
    return output


def _parse_transcripts(symbol: str, data: dict[str, Any], fetched_at: datetime) -> list[TranscriptRecord]:
    output: list[TranscriptRecord] = []
    for row in _dict_rows(data.get("transcripts")):
        row_symbol = str(_pick(row, "symbol") or symbol).upper()
        if row_symbol != symbol:
            continue
        content = _text(_pick(row, "content", "transcript", "text"))
        call_date = _date(_pick(row, "date", "callDate", "call_date"))
        quality: dict[str, Any] = {}
        if not content:
            quality["content_missing"] = True
        output.append(
            TranscriptRecord(
                symbol=symbol,
                fiscal_year=_int(_pick(row, "year", "fiscalYear", "calendarYear")),
                fiscal_period=_text(_pick(row, "period", "quarter", "fiscal_period")),
                call_date=call_date,
                transcript_text=content,
                word_count=len(content.split()) if content else None,
                source_published_at=(_datetime(call_date) if call_date else None) or fetched_at,
                value_json={key: value for key, value in row.items() if key not in {"content", "transcript", "text"}},
                quality_flags=quality,
            )
        )
    return output


def _parse_transcript_documents(symbol: str, data: dict[str, Any], fetched_at: datetime) -> list[SourceDocumentRecord]:
    output: list[SourceDocumentRecord] = []
    for row in _dict_rows(data.get("transcripts")):
        row_symbol = str(_pick(row, "symbol") or symbol).upper()
        if row_symbol != symbol:
            continue
        year = _int(_pick(row, "year", "fiscalYear", "calendarYear"))
        period = _text(_pick(row, "period", "quarter", "fiscal_period"))
        content = _text(_pick(row, "content", "transcript", "text"))
        call_date = _date(_pick(row, "date", "callDate", "call_date"))
        key = _compact_key("earning_transcript", str(year) if year else None, period)
        if not key:
            continue
        output.append(
            SourceDocumentRecord(
                symbol=symbol,
                document_type="earning_transcript",
                document_key=key,
                title=" ".join(item for item in ["Earnings call transcript", str(year) if year else None, period] if item),
                source_event_at=_datetime(call_date) if call_date else None,
                source_published_at=(_datetime(call_date) if call_date else None) or fetched_at,
                content_text=content,
                metadata_json={"fiscal_year": year, "fiscal_period": period, "call_date": str(call_date) if call_date else None},
                quality_flags={} if content else {"content_text_missing": True},
            )
        )
    return output


def _parse_macro_events(data: dict[str, Any], fetched_at: datetime) -> list[MacroEventRecord]:
    output: list[MacroEventRecord] = []
    for row in _dict_rows(data.get("events")):
        event_name = _text(_pick(row, "event", "eventName", "name"))
        if not event_name:
            continue
        release_at = _datetime(_pick(row, "date", "releaseDate", "release_at"))
        provider_event_id = _text(_pick(row, "id", "eventId", "provider_event_id"))
        country = _text(_pick(row, "country"))
        currency = _text(_pick(row, "currency"))
        unit = _text(_pick(row, "unit")) or _infer_unit(_pick(row, "actual", "estimate", "previous"))
        raw_json = dict(row)
        payload_hash = _stable_hash(raw_json)
        event_key = _macro_event_key(
            provider_event_id=provider_event_id,
            country=country,
            currency=currency,
            event_name=event_name,
            release_at=release_at,
        )
        output.append(
            MacroEventRecord(
                source="fmp",
                provider_event_id=provider_event_id,
                event_key=event_key,
                event_name=event_name,
                event_name_cn=None,
                country=country,
                currency=currency,
                release_at_utc=release_at,
                impact=_text(_pick(row, "impact")),
                actual_raw=_raw_text(_pick(row, "actual")),
                estimate_raw=_raw_text(_pick(row, "estimate")),
                previous_raw=_raw_text(_pick(row, "previous")),
                actual_value=_macro_decimal(_pick(row, "actual")),
                estimate_value=_macro_decimal(_pick(row, "estimate")),
                previous_value=_macro_decimal(_pick(row, "previous")),
                unit=unit,
                observed_at_utc=fetched_at if fetched_at.tzinfo else fetched_at.replace(tzinfo=UTC),
                payload_hash=payload_hash,
                raw_json=raw_json,
            )
        )
    return output


def _parse_metrics(symbol: str, data: dict[str, Any], fetched_at: datetime, currency: str) -> list[MetricRecord]:
    metrics = _parse_profile_metrics(symbol, data.get("profile") or {}, fetched_at, currency)
    target = data.get("price_target") or {}
    target_summary = data.get("price_target_summary") or {}
    grades = data.get("grades_consensus") or {}
    ratings = data.get("ratings_snapshot") or {}

    _append_numeric_metric(
        metrics,
        symbol=symbol,
        code="analyst_target_median",
        name="目标价中位数",
        description="FMP price-target-consensus.targetMedian。",
        value=_decimal(_pick(target, "targetMedian", "target_median")),
        event_at=fetched_at,
        unit="price",
        currency=currency,
    )
    _append_json_metric(
        metrics,
        symbol=symbol,
        code="analyst_target_summary",
        name="目标价历史汇总",
        description="FMP price-target-summary 返回的目标价历史区间汇总。",
        value=target_summary,
        event_at=fetched_at,
    )
    _append_text_metric(
        metrics,
        symbol=symbol,
        code="analyst_rating_consensus",
        name="分析师评级共识",
        description="FMP grades-consensus.consensus。",
        value=_pick(grades, "consensus"),
        event_at=fetched_at,
    )
    _append_text_metric(
        metrics,
        symbol=symbol,
        code="fmp_rating",
        name="FMP综合评级",
        description="FMP ratings-snapshot.rating。",
        value=_pick(ratings, "rating"),
        event_at=fetched_at,
    )
    _append_numeric_metric(
        metrics,
        symbol=symbol,
        code="fmp_rating_overall_score",
        name="FMP综合评分",
        description="FMP ratings-snapshot.overallScore。",
        value=_decimal(_pick(ratings, "overallScore")),
        event_at=fetched_at,
        unit="score",
    )
    score_payload = {key: ratings[key] for key in ratings if key.endswith("Score") and key != "overallScore"}
    _append_json_metric(
        metrics,
        symbol=symbol,
        code="fmp_rating_scores",
        name="FMP评分明细",
        description="FMP ratings-snapshot 中除综合评分外的分项评分。",
        value=score_payload,
        event_at=fetched_at,
    )
    return metrics


def _parse_profile_metrics(symbol: str, profile: dict[str, Any], fetched_at: datetime, currency: str) -> list[MetricRecord]:
    metrics: list[MetricRecord] = []
    _append_numeric_metric(
        metrics,
        symbol=symbol,
        code="market_cap",
        name="市值",
        description="FMP profile.marketCap。",
        value=_decimal(_pick(profile, "marketCap", "market_cap")),
        event_at=fetched_at,
        unit="currency",
        currency=currency,
    )
    _append_numeric_metric(
        metrics,
        symbol=symbol,
        code="profile_price",
        name="画像价格",
        description="FMP profile.price，作为公司画像接口返回的快照价格。",
        value=_decimal(_pick(profile, "price")),
        event_at=fetched_at,
        unit="price",
        currency=currency,
    )
    _append_numeric_metric(
        metrics,
        symbol=symbol,
        code="beta",
        name="Beta",
        description="FMP profile.beta。",
        value=_decimal(_pick(profile, "beta")),
        event_at=fetched_at,
    )
    _append_numeric_metric(
        metrics,
        symbol=symbol,
        code="average_volume",
        name="平均成交量",
        description="FMP profile.averageVolume。",
        value=_decimal(_pick(profile, "averageVolume", "average_volume")),
        event_at=fetched_at,
        unit="shares",
    )
    return metrics


def _append_numeric_metric(
    metrics: list[MetricRecord],
    *,
    symbol: str,
    code: str,
    name: str,
    description: str,
    value: Decimal | None,
    event_at: datetime,
    unit: str | None = None,
    currency: str | None = None,
) -> None:
    if value is None:
        return
    metrics.append(
        MetricRecord(
            symbol=symbol,
            metric_code=code,
            event_at=event_at,
            value_numeric=value,
            unit=unit,
            currency=currency,
            display_name_zh=name,
            description_zh=description,
            value_type="numeric",
        )
    )


def _append_text_metric(
    metrics: list[MetricRecord],
    *,
    symbol: str,
    code: str,
    name: str,
    description: str,
    value: Any,
    event_at: datetime,
) -> None:
    if value is None or value == "":
        return
    metrics.append(
        MetricRecord(
            symbol=symbol,
            metric_code=code,
            event_at=event_at,
            value_text=str(value),
            display_name_zh=name,
            description_zh=description,
            value_type="text",
        )
    )


def _append_json_metric(
    metrics: list[MetricRecord],
    *,
    symbol: str,
    code: str,
    name: str,
    description: str,
    value: dict[str, Any],
    event_at: datetime,
) -> None:
    if not value:
        return
    metrics.append(
        MetricRecord(
            symbol=symbol,
            metric_code=code,
            event_at=event_at,
            value_json=value,
            display_name_zh=name,
            description_zh=description,
            value_type="json",
        )
    )


def _pick(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in row:
            value = row[name]
            if value is not None and value != "":
                return value
    return None


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _macro_decimal(value: Any) -> Decimal | None:
    text = _raw_text(value)
    if text is None:
        return None
    normalized = text.replace(",", "").replace("%", "").strip()
    multiplier = Decimal("1")
    if normalized and normalized[-1].upper() in {"K", "M", "B"}:
        suffix = normalized[-1].upper()
        normalized = normalized[:-1].strip()
        multiplier = {"K": Decimal("1000"), "M": Decimal("1000000"), "B": Decimal("1000000000")}[suffix]
    match = re.search(r"[-+]?\d+(?:\.\d+)?", normalized)
    if not match:
        return None
    try:
        return Decimal(match.group(0)) * multiplier
    except (InvalidOperation, ValueError):
        return None


def _int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed_date = date.fromisoformat(text[:10])
        except ValueError:
            return None
        return datetime(parsed_date.year, parsed_date.month, parsed_date.day, tzinfo=UTC)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _raw_text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def _financial_period_type(value: Any) -> str:
    raw = str(value or "").lower()
    if raw in {"quarter", "quarterly", "q", "q1", "q2", "q3", "q4"}:
        return "quarter"
    if raw in {"annual", "fy", "fiscal_year", "year"}:
        return "fiscal_year"
    if raw == "ttm":
        return "ttm"
    return "unknown"


def _bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    raw = str(value).strip().lower()
    if raw in {"1", "true", "yes", "y"}:
        return True
    if raw in {"0", "false", "no", "n"}:
        return False
    return None


def _compact_key(*parts: str | None) -> str:
    return ":".join(part for part in parts if part)


def _macro_event_key(
    *,
    provider_event_id: str | None,
    country: str | None,
    currency: str | None,
    event_name: str,
    release_at: datetime | None,
) -> str:
    if provider_event_id:
        return f"fmp:{provider_event_id}"
    release_date = release_at.date().isoformat() if release_at else ""
    raw = "|".join([country or "", currency or "", event_name, release_date]).lower()
    return "fmp:macro:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _stable_hash(value: dict[str, Any]) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _infer_unit(value: Any) -> str | None:
    text = _raw_text(value)
    if not text:
        return None
    if "%" in text:
        return "%"
    stripped = text.strip()
    if stripped and stripped[-1].upper() in {"K", "M", "B"}:
        return stripped[-1].upper()
    return None


def _session(value: Any) -> str:
    raw = str(value or "").lower()
    if raw in {"bmo", "before_open", "before market open", "amc-before"}:
        return "before_open"
    if raw in {"amc", "after_close", "after market close"}:
        return "after_close"
    if raw in {"dmt", "during_market", "during market"}:
        return "during_market"
    return "unknown"


def _clean_cik(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value).zfill(10)


def _quality_high_low(**values: Decimal | None) -> dict[str, Any]:
    flags: dict[str, Any] = {}
    if values["eps_high"] is not None and values["eps_low"] is not None and values["eps_high"] < values["eps_low"]:
        flags["eps_high_below_low"] = True
    if values["revenue_high"] is not None and values["revenue_low"] is not None and values["revenue_high"] < values["revenue_low"]:
        flags["revenue_high_below_low"] = True
    return flags
