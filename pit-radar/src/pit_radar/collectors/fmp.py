from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
import http.client
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, date, datetime
from typing import Any, Callable

from pit_radar.collectors.base import CollectionContext, CollectionResult, RawCollectionItem
from pit_radar.config import Settings, get_settings


FINANCIAL_ENDPOINTS = {
    "income_statement": "/stable/income-statement",
    "balance_sheet": "/stable/balance-sheet-statement",
    "cash_flow": "/stable/cash-flow-statement",
    "ratios": "/stable/ratios",
    "key_metrics": "/stable/key-metrics",
    "financial_growth": "/stable/financial-growth",
}

_RATE_LIMITERS: dict[int, "_RateLimiter"] = {}
_RATE_LIMITERS_LOCK = threading.Lock()


class _RateLimiter:
    def __init__(self, requests_per_minute: int):
        self.requests_per_minute = max(1, requests_per_minute)
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                cutoff = now - 60.0
                while self._timestamps and self._timestamps[0] <= cutoff:
                    self._timestamps.popleft()
                if len(self._timestamps) < self.requests_per_minute:
                    self._timestamps.append(now)
                    return
                sleep_for = max(0.05, 60.0 - (now - self._timestamps[0]))
            time.sleep(sleep_for)


def _rate_limiter_for(requests_per_minute: int) -> _RateLimiter:
    with _RATE_LIMITERS_LOCK:
        limiter = _RATE_LIMITERS.get(requests_per_minute)
        if limiter is None:
            limiter = _RateLimiter(requests_per_minute)
            _RATE_LIMITERS[requests_per_minute] = limiter
        return limiter


class FmpClient:
    def __init__(self, settings: Settings | None = None, timeout_seconds: int = 30, max_retries: int | None = None):
        self.settings = settings or get_settings()
        if not self.settings.fmp_api_key:
            raise RuntimeError("FMP_API_KEY is required for FMP collectors.")
        self.rate_limiter = _rate_limiter_for(self.settings.fmp_rate_limit_per_minute)
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(1, max_retries if max_retries is not None else self.settings.fmp_max_retries)

    def get_json(self, path: str, params: dict[str, str]) -> tuple[Any, int]:
        query = dict(params)
        headers = {"User-Agent": "pit-radar/0.1"}
        if self.settings.fmp_auth_mode == "header":
            headers["Authorization"] = f"Bearer {self.settings.fmp_api_key}"
        else:
            query["apikey"] = self.settings.fmp_api_key
        url = f"{self.settings.fmp_base_url}{path}?{urllib.parse.urlencode(query)}"
        request = urllib.request.Request(url, headers=headers)
        for attempt in range(self.max_retries):
            try:
                self.rate_limiter.acquire()
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    return json.loads(response.read().decode("utf-8")), response.status
            except http.client.IncompleteRead as exc:
                if attempt == self.max_retries - 1:
                    raise RuntimeError(f"FMP {path} incomplete read after retries: {len(exc.partial)} bytes read") from exc
                time.sleep(_connection_retry_delay(attempt))
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                if exc.code == 429 and attempt < self.max_retries - 1:
                    retry_after = exc.headers.get("Retry-After")
                    wait_seconds = int(retry_after) if retry_after and retry_after.isdigit() else 60
                    time.sleep(wait_seconds)
                    continue
                raise RuntimeError(f"FMP {path} failed: {exc.code} {body[:300]}") from exc
            except (http.client.RemoteDisconnected, TimeoutError, urllib.error.URLError) as exc:
                if attempt == self.max_retries - 1:
                    raise RuntimeError(f"FMP {path} connection failed after retries: {exc}") from exc
                time.sleep(_connection_retry_delay(attempt))
        raise RuntimeError(f"FMP {path} failed after retries")


def _connection_retry_delay(attempt: int) -> float:
    return min(5.0, 3.0 + 2.0 * attempt)


def _collect_symbol_items(
    symbols: list[str],
    max_workers: int,
    collect_symbol: Callable[[str], RawCollectionItem],
) -> CollectionResult:
    items_by_symbol: dict[str, RawCollectionItem] = {}
    errors: list[str] = []
    if max_workers <= 1 or len(symbols) <= 1:
        for symbol in symbols:
            try:
                items_by_symbol[symbol] = collect_symbol(symbol)
            except Exception as exc:
                errors.append(f"{symbol}: {exc}")
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(collect_symbol, symbol): symbol for symbol in symbols}
            for future in as_completed(future_map):
                symbol = future_map[future]
                try:
                    items_by_symbol[symbol] = future.result()
                except Exception as exc:
                    errors.append(f"{symbol}: {exc}")
    items = [items_by_symbol[symbol] for symbol in symbols if symbol in items_by_symbol]
    return CollectionResult(items=items, errors=errors)


class FmpEstimatesCollector:
    dataset_code = "estimates"
    source_code = "fmp"

    def __init__(self, client: FmpClient | None = None, max_workers: int = 1, include_profile: bool = True):
        self.client = client or FmpClient()
        self.max_workers = max(1, max_workers)
        self.include_profile = include_profile

    async def collect(self, context: CollectionContext) -> CollectionResult:
        return _collect_symbol_items(context.symbols, self.max_workers, self._collect_symbol)

    def _collect_symbol(self, symbol: str) -> RawCollectionItem:
        warnings: list[str] = []
        estimates: list[Any] = []
        status = 200
        for period in ("annual", "quarter"):
            try:
                period_rows, status = self.client.get_json(
                    "/stable/analyst-estimates",
                    {"symbol": symbol, "period": period, "page": "0", "limit": "10"},
                )
            except Exception as exc:
                warnings.append(f"{symbol} analyst-estimates {period}: {exc}")
                continue
            rows = _as_list(period_rows)
            for row in rows:
                if isinstance(row, dict):
                    row.setdefault("period", period)
                estimates.append(row)
        if not estimates:
            raise RuntimeError("no analyst estimates returned")
        price_target = _optional_json(self.client, warnings, symbol, "price-target-consensus", "/stable/price-target-consensus", {"symbol": symbol})
        price_target_summary = _optional_json(
            self.client, warnings, symbol, "price-target-summary", "/stable/price-target-summary", {"symbol": symbol}
        )
        grades = _optional_json(self.client, warnings, symbol, "grades-consensus", "/stable/grades-consensus", {"symbol": symbol})
        ratings = _optional_json(self.client, warnings, symbol, "ratings-snapshot", "/stable/ratings-snapshot", {"symbol": symbol})
        profile = _optional_json(self.client, warnings, symbol, "profile", "/stable/profile", {"symbol": symbol}) if self.include_profile else {}
        return RawCollectionItem(
            request_key=f"fmp-estimates:{symbol}",
            data={
                "symbol": symbol,
                "profile": _first(profile),
                "estimates": estimates,
                "price_target": _first(price_target),
                "price_target_summary": _first(price_target_summary),
                "grades_consensus": _first(grades),
                "ratings_snapshot": _first(ratings),
            },
            http_status=status,
            metadata={"warnings": warnings} if warnings else {},
        )


class FmpDailyBarsCollector:
    dataset_code = "daily_bars"
    source_code = "fmp"

    def __init__(self, client: FmpClient | None = None, include_profile: bool = True, max_workers: int = 1):
        self.client = client or FmpClient()
        self.include_profile = include_profile
        self.max_workers = max(1, max_workers)

    async def collect(self, context: CollectionContext) -> CollectionResult:
        if self.max_workers == 1 or len(context.symbols) <= 1:
            return self._collect_serial(context)
        return self._collect_parallel(context)

    def _collect_serial(self, context: CollectionContext) -> CollectionResult:
        items: list[RawCollectionItem] = []
        errors: list[str] = []
        for symbol in context.symbols:
            try:
                items.append(self._collect_symbol(symbol, context))
            except Exception as exc:
                errors.append(f"{symbol}: {exc}")
        return CollectionResult(items=items, errors=errors)

    def _collect_parallel(self, context: CollectionContext) -> CollectionResult:
        items_by_symbol: dict[str, RawCollectionItem] = {}
        errors: list[str] = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_map = {executor.submit(self._collect_symbol, symbol, context): symbol for symbol in context.symbols}
            for future in as_completed(future_map):
                symbol = future_map[future]
                try:
                    items_by_symbol[symbol] = future.result()
                except Exception as exc:
                    errors.append(f"{symbol}: {exc}")
        items = [items_by_symbol[symbol] for symbol in context.symbols if symbol in items_by_symbol]
        return CollectionResult(items=items, errors=errors)

    def _collect_symbol(self, symbol: str, context: CollectionContext) -> RawCollectionItem:
        warnings: list[str] = []
        params = {"symbol": symbol}
        if context.from_date:
            params["from"] = str(context.from_date)
        if context.to_date:
            params["to"] = str(context.to_date)
        bars, status = self.client.get_json("/stable/historical-price-eod/full", params)
        profile = _optional_json(self.client, warnings, symbol, "profile", "/stable/profile", {"symbol": symbol}) if self.include_profile else {}
        return RawCollectionItem(
            request_key=f"fmp-daily-bars:{symbol}:{context.from_date}:{context.to_date}",
            data={"symbol": symbol, "profile": _first(profile), "historical": _extract_bars(bars)},
            http_status=status,
            metadata={"warnings": warnings} if warnings else {},
        )


class FmpEarningsCollector:
    dataset_code = "earnings"
    source_code = "fmp"

    def __init__(self, client: FmpClient | None = None, max_workers: int = 1, include_profile: bool = True):
        self.client = client or FmpClient()
        self.max_workers = max(1, max_workers)
        self.include_profile = include_profile

    async def collect(self, context: CollectionContext) -> CollectionResult:
        return _collect_symbol_items(context.symbols, self.max_workers, self._collect_symbol)

    def _collect_symbol(self, symbol: str) -> RawCollectionItem:
        warnings: list[str] = []
        earnings, status = self.client.get_json("/stable/earnings", {"symbol": symbol})
        profile = _optional_json(self.client, warnings, symbol, "profile", "/stable/profile", {"symbol": symbol}) if self.include_profile else {}
        earnings_rows = _as_list(earnings)
        return RawCollectionItem(
            request_key=f"fmp-earnings:{symbol}",
            data={"symbol": symbol, "profile": _first(profile), "earnings": earnings_rows},
            http_status=status,
            source_published_at=_latest_date_field(earnings_rows, "lastUpdated"),
            metadata={"warnings": warnings} if warnings else {},
        )


class FmpNewsCollector:
    dataset_code = "news"
    source_code = "fmp"

    def __init__(self, client: FmpClient | None = None, limit: int = 50, max_workers: int = 1, include_profile: bool = True):
        self.client = client or FmpClient()
        self.limit = limit
        self.max_workers = max(1, max_workers)
        self.include_profile = include_profile

    async def collect(self, context: CollectionContext) -> CollectionResult:
        return _collect_symbol_items(context.symbols, self.max_workers, lambda symbol: self._collect_symbol(symbol, context))

    def _collect_symbol(self, symbol: str, context: CollectionContext) -> RawCollectionItem:
        warnings: list[str] = []
        params = {"symbols": symbol, "limit": str(self.limit)}
        if context.from_date:
            params["from"] = str(context.from_date)
        if context.to_date:
            params["to"] = str(context.to_date)
        stock_news = _optional_json(
            self.client,
            warnings,
            symbol,
            "stock-news",
            "/stable/news/stock",
            params,
        )
        press_releases = _optional_json(
            self.client,
            warnings,
            symbol,
            "press-releases",
            "/stable/news/press-releases",
            params,
        )
        news_rows = _tag_news(_as_list(stock_news), "stock_news") + _tag_news(_as_list(press_releases), "press_release")
        news_rows = _filter_news_date_range(news_rows, context.from_date, context.to_date)
        if not news_rows:
            warnings.append(f"{symbol} news: no matching news returned")
        profile = _optional_json(self.client, warnings, symbol, "profile", "/stable/profile", {"symbol": symbol}) if self.include_profile else {}
        return RawCollectionItem(
            request_key=f"fmp-news:{symbol}:{context.from_date}:{context.to_date}:{self.limit}",
            data={"symbol": symbol, "profile": _first(profile), "news": news_rows},
            http_status=200,
            source_published_at=_latest_date_field(news_rows, "publishedDate"),
            metadata={"warnings": warnings} if warnings else {},
        )


class FmpFinancialsCollector:
    dataset_code = "financials"
    source_code = "fmp"

    def __init__(
        self,
        client: FmpClient | None = None,
        periods: tuple[str, ...] = ("annual", "quarter"),
        limit: int = 8,
        max_workers: int = 1,
        include_profile: bool = True,
    ):
        self.client = client or FmpClient()
        self.periods = periods
        self.limit = limit
        self.max_workers = max(1, max_workers)
        self.include_profile = include_profile

    async def collect(self, context: CollectionContext) -> CollectionResult:
        return _collect_symbol_items(context.symbols, self.max_workers, self._collect_symbol)

    def _collect_symbol(self, symbol: str) -> RawCollectionItem:
        warnings: list[str] = []
        financials: dict[str, list[dict[str, Any]]] = {key: [] for key in FINANCIAL_ENDPOINTS}
        for period in self.periods:
            for dataset_code, path in FINANCIAL_ENDPOINTS.items():
                rows = _optional_json(
                    self.client,
                    warnings,
                    symbol,
                    f"{dataset_code}:{period}",
                    path,
                    {"symbol": symbol, "period": period, "limit": str(self.limit)},
                )
                financials[dataset_code].extend(_tag_period(_as_list(rows), period))

        scores = _optional_json(
            self.client,
            warnings,
            symbol,
            "financial-scores",
            "/stable/financial-scores",
            {"symbol": symbol},
        )
        financials["financial_scores"] = _as_dict_rows(scores)
        if not any(financials.values()):
            raise RuntimeError("no financial facts returned")

        profile = _optional_json(self.client, warnings, symbol, "profile", "/stable/profile", {"symbol": symbol}) if self.include_profile else {}
        all_rows = [row for rows in financials.values() for row in rows]
        return RawCollectionItem(
            request_key=f"fmp-financials:{symbol}:{','.join(self.periods)}:{self.limit}",
            data={"symbol": symbol, "profile": _first(profile), "financials": financials},
            http_status=200,
            source_published_at=_latest_any_date_field(all_rows, ("acceptedDate", "filingDate", "fillingDate", "date")),
            metadata={"warnings": warnings} if warnings else {},
        )


class FmpSecFilingsCollector:
    dataset_code = "sec_filings"
    source_code = "fmp"

    def __init__(
        self,
        client: FmpClient | None = None,
        form_types: tuple[str, ...] = ("8-K",),
        limit: int = 100,
        max_workers: int = 1,
        include_profile: bool = True,
    ):
        self.client = client or FmpClient()
        self.form_types = tuple(item.upper() for item in form_types if item)
        self.limit = limit
        self.max_workers = max(1, max_workers)
        self.include_profile = include_profile

    async def collect(self, context: CollectionContext) -> CollectionResult:
        return _collect_symbol_items(context.symbols, self.max_workers, lambda symbol: self._collect_symbol(symbol, context))

    def _collect_symbol(self, symbol: str, context: CollectionContext) -> RawCollectionItem:
        warnings: list[str] = []
        params = {"symbol": symbol, "page": "0", "limit": str(self.limit)}
        if context.from_date:
            params["from"] = str(context.from_date)
        if context.to_date:
            params["to"] = str(context.to_date)
        rows, status = self.client.get_json("/stable/sec-filings-search/symbol", params)
        filings = _filter_form_types(_as_dict_rows(rows), self.form_types)
        if not filings:
            warnings.append(f"{symbol} sec-filings: no matching filings returned")
        profile = _optional_json(self.client, warnings, symbol, "profile", "/stable/profile", {"symbol": symbol}) if self.include_profile else {}
        return RawCollectionItem(
            request_key=f"fmp-sec-filings:{symbol}:{context.from_date}:{context.to_date}:{','.join(self.form_types)}:{self.limit}",
            data={"symbol": symbol, "profile": _first(profile), "sec_filings": filings},
            http_status=status,
            source_published_at=_latest_any_date_field(filings, ("acceptedDate", "filingDate", "fillingDate")),
            metadata={"warnings": warnings} if warnings else {},
        )


class FmpTranscriptsCollector:
    dataset_code = "transcripts"
    source_code = "fmp"

    def __init__(
        self,
        client: FmpClient | None = None,
        periods: tuple[tuple[int, int], ...] = (),
    ):
        self.client = client or FmpClient()
        self.periods = periods

    async def collect(self, context: CollectionContext) -> CollectionResult:
        items: list[RawCollectionItem] = []
        errors: list[str] = []
        if not self.periods:
            return CollectionResult(items=[], errors=["transcript periods are required, e.g. 2025:4"])
        for symbol in context.symbols:
            warnings: list[str] = []
            transcripts: list[dict[str, Any]] = []
            status = 200
            try:
                for year, quarter in self.periods:
                    try:
                        rows, status = self.client.get_json(
                            "/stable/earning-call-transcript",
                            {"symbol": symbol, "year": str(year), "quarter": str(quarter)},
                        )
                    except Exception as exc:
                        warnings.append(f"{symbol} transcript {year}:Q{quarter}: {exc}")
                        continue
                    transcripts.extend(_as_dict_rows(rows))
                if not transcripts:
                    warnings.append(f"{symbol} transcripts: no matching transcripts returned")
                profile = _optional_json(self.client, warnings, symbol, "profile", "/stable/profile", {"symbol": symbol})
                period_key = ",".join(f"{year}:Q{quarter}" for year, quarter in self.periods)
                items.append(
                    RawCollectionItem(
                        request_key=f"fmp-transcripts:{symbol}:{period_key}",
                        data={"symbol": symbol, "profile": _first(profile), "transcripts": transcripts},
                        http_status=status,
                        source_published_at=_latest_any_date_field(transcripts, ("date",)),
                        metadata={"warnings": warnings} if warnings else {},
                    )
                )
            except Exception as exc:
                errors.append(f"{symbol}: {exc}")
        return CollectionResult(items=items, errors=errors)


class FmpMacroCalendarCollector:
    dataset_code = "macro_events"
    source_code = "fmp"

    def __init__(
        self,
        client: FmpClient | None = None,
        countries: tuple[str, ...] = ("US",),
    ):
        self.client = client or FmpClient()
        self.countries = tuple(country.upper() for country in countries if country)

    async def collect(self, context: CollectionContext) -> CollectionResult:
        params: dict[str, str] = {}
        if context.from_date:
            params["from"] = str(context.from_date)
        if context.to_date:
            params["to"] = str(context.to_date)
        try:
            rows, status = self.client.get_json("/stable/economic-calendar", params)
            events = _filter_macro_countries(_as_dict_rows(rows), self.countries)
            item = RawCollectionItem(
                request_key=f"fmp-macro-calendar:{context.from_date}:{context.to_date}:{','.join(self.countries)}",
                data={"events": events, "filters": {"countries": list(self.countries), "from": str(context.from_date), "to": str(context.to_date)}},
                http_status=status,
                source_published_at=_latest_any_date_field(events, ("date",)),
                metadata={"total_rows": len(_as_dict_rows(rows)), "kept_rows": len(events)},
            )
            return CollectionResult(items=[item])
        except Exception as exc:
            return CollectionResult(items=[], errors=[f"macro_events: {exc}"])


def _first(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        return value[0] if value else {}
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None or value == "":
        return []
    return [value]


def _as_dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in _as_list(value) if isinstance(row, dict)]


def _tag_period(rows: list[Any], period: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        item.setdefault("period", period)
        output.append(item)
    return output


def _tag_news(rows: list[Any], news_type: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        item["_news_type"] = news_type
        output.append(item)
    return output


def _filter_form_types(rows: list[dict[str, Any]], form_types: tuple[str, ...]) -> list[dict[str, Any]]:
    if not form_types:
        return rows
    allowed = {item.upper() for item in form_types}
    return [row for row in rows if str(row.get("formType") or row.get("form_type") or "").upper() in allowed]


def _filter_news_date_range(rows: list[dict[str, Any]], from_date: date | None, to_date: date | None) -> list[dict[str, Any]]:
    if from_date is None and to_date is None:
        return rows
    output: list[dict[str, Any]] = []
    for row in rows:
        published = _row_date(row, ("publishedDate", "date", "published_at"))
        if published is None:
            continue
        if from_date and published < from_date:
            continue
        if to_date and published > to_date:
            continue
        output.append(row)
    return output


def _filter_macro_countries(rows: list[dict[str, Any]], countries: tuple[str, ...]) -> list[dict[str, Any]]:
    if not countries:
        return rows
    allowed = {country.upper() for country in countries}
    return [row for row in rows if str(row.get("country") or "").upper() in allowed]


def _row_date(row: dict[str, Any], fields: tuple[str, ...]) -> date | None:
    for field in fields:
        value = row.get(field)
        if not value:
            continue
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            continue
    return None


def _extract_bars(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict) and isinstance(value.get("historical"), list):
        return value["historical"]
    if isinstance(value, list):
        return value
    return []


def _optional_json(
    client: FmpClient,
    warnings: list[str],
    symbol: str,
    label: str,
    path: str,
    params: dict[str, str],
) -> Any:
    try:
        value, _ = client.get_json(path, params)
        return value
    except Exception as exc:
        warnings.append(f"{symbol} {label}: {exc}")
        return []


def _latest_date_field(rows: list[Any], field: str) -> datetime | None:
    return _latest_any_date_field(rows, (field,))


def _latest_any_date_field(rows: list[Any], fields: tuple[str, ...]) -> datetime | None:
    dates: list[datetime] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for field in fields:
            if not row.get(field):
                continue
            try:
                dates.append(datetime.fromisoformat(str(row[field])[:10]).replace(tzinfo=UTC))
            except ValueError:
                continue
    return max(dates) if dates else None
