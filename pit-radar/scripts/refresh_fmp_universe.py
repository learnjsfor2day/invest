#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, time as datetime_time, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pit_radar.collectors.fmp import FmpClient
from pit_radar.config import get_settings

DEFAULT_SYMBOLS_FILE = Path("data/universe/daily_symbols.txt")
DEFAULT_ACCEPTED_CSV = Path("data/universe/daily_universe.csv")
DEFAULT_REJECTED_CSV = Path("data/universe/daily_universe_rejected.csv")
DEFAULT_MANIFEST = Path("data/universe/refresh_manifest.json")
NY_TZ = ZoneInfo("America/New_York")

EXCLUDED_SYMBOLS: set[str] = set()

EXCLUDED_NAME_PATTERNS: list[re.Pattern[str]] = []

BAD_SYMBOL_SUFFIXES = {
    "P",
    "PA",
    "PB",
    "PC",
    "PD",
    "PE",
    "PF",
    "PG",
    "PH",
    "PI",
    "PJ",
    "PK",
    "PL",
    "PM",
    "PN",
    "PO",
    "PP",
    "PQ",
    "PR",
    "PS",
    "PT",
    "PU",
    "PV",
    "PW",
    "PX",
    "PY",
    "PZ",
    "PR",
    "PRA",
    "PRB",
    "PRC",
    "PRD",
    "PRE",
    "PRF",
    "PRG",
    "PRH",
    "PRI",
    "PRJ",
    "PRK",
    "PRL",
    "PRM",
    "PRN",
    "PRO",
    "PRP",
    "PRQ",
    "PRR",
    "PRS",
    "PRT",
    "PRU",
    "PRV",
    "PRW",
    "PRX",
    "PRY",
    "PRZ",
    "R",
    "RT",
    "U",
    "UN",
    "UNIT",
    "W",
    "WS",
    "WT",
    "WTA",
    "WTB",
    "WTC",
}

BAD_NAME_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bwarrants?\b",
        r"\bright(s)?\b",
        r"\bunits?\b",
        r"\bpreferred (stock|shares?)\b",
        r"\bpreference shares?\b",
        r"\bdepositary shares?\b",
        r"\bsenior notes?\b",
        r"\bsubordinated notes?\b",
        r"\bexchange[- ]traded fund\b",
        r"\betf\b",
        r"\bclosed[- ]end fund\b",
        r"\bclosed[- ]end investment\b",
    ]
]


@dataclass(frozen=True)
class UniverseCriteria:
    country: str
    exchanges: tuple[str, ...]
    min_market_cap: Decimal
    min_volume: Decimal
    min_dollar_volume: Decimal
    min_price: Decimal
    max_symbols: int


@dataclass(frozen=True)
class UniverseRow:
    symbol: str
    company_name: str
    market_cap: Decimal | None
    price: Decimal | None
    volume: Decimal | None
    dollar_volume: Decimal | None
    exchange: str
    exchange_short_name: str
    country: str
    sector: str
    industry: str
    is_etf: bool | None
    is_fund: bool | None
    is_actively_trading: bool | None
    reason: str = ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh the semi-monthly US stock universe from FMP company-screener.")
    parser.add_argument("--output-symbols", default=str(DEFAULT_SYMBOLS_FILE), help="Output ticker list used by daily_fmp_batch.py.")
    parser.add_argument("--output-csv", default=str(DEFAULT_ACCEPTED_CSV), help="Detailed accepted universe CSV.")
    parser.add_argument("--rejected-csv", default=str(DEFAULT_REJECTED_CSV), help="Rejected rows and reasons CSV.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="Refresh manifest JSON.")
    parser.add_argument("--country", default="", help="Optional company domicile country filter; empty means all US-listed companies.")
    parser.add_argument("--exchanges", default="NASDAQ,NYSE,AMEX", help="Allowed exchangeShortName values.")
    parser.add_argument("--min-market-cap", type=Decimal, default=Decimal("20000000"), help="Minimum market cap in USD.")
    parser.add_argument("--min-volume", type=Decimal, default=Decimal("3000"), help="Minimum share volume.")
    parser.add_argument("--min-dollar-volume", type=Decimal, default=Decimal("20000"), help="Minimum price * volume.")
    parser.add_argument("--min-price", type=Decimal, default=Decimal("1"), help="Minimum stock price.")
    parser.add_argument("--limit", type=int, default=1000, help="FMP screener page size.")
    parser.add_argument("--target-symbols", type=int, default=4000, help="Stop after at least this many pre-validation candidates pass local filters.")
    parser.add_argument("--max-pages", type=int, default=20, help="Maximum screener pages to request per exchange.")
    parser.add_argument("--max-page-errors", type=int, default=8, help="Abort screener paging after this many failed pages.")
    parser.add_argument("--failed-page-retry-rounds", type=int, default=2, help="Extra retry rounds for failed screener exchange/page pairs.")
    parser.add_argument("--screener-timeout-seconds", type=int, default=30, help="Timeout for each screener page request.")
    parser.add_argument("--screener-max-retries", type=int, default=3, help="Total attempts for each screener page request.")
    parser.add_argument("--max-symbols", type=int, default=0, help="Cap the final universe after sorting by market cap; 0 means no cap.")
    parser.add_argument("--min-accepted", type=int, default=4000, help="Abort before writing if accepted symbols are below this count.")
    parser.add_argument("--allow-small-universe", action="store_true", help="Write outputs even when accepted symbols are below --min-accepted.")
    parser.add_argument("--price-validation-date", help="Trading date used to verify OHLCV availability. Defaults to previous New York business day.")
    parser.add_argument("--validation-method", choices=["batch-quote", "daily-bar", "none"], default="none", help="How to verify candidate tradability.")
    parser.add_argument("--skip-price-validation", action="store_true", help="Deprecated alias for --validation-method none.")
    parser.add_argument("--quote-chunk-size", type=int, default=100, help="Symbols per batch-quote validation request.")
    parser.add_argument("--validation-timeout-seconds", type=int, default=10, help="Timeout for each price validation request.")
    parser.add_argument("--validation-max-retries", type=int, default=2, help="Retries for each price validation request.")
    parser.add_argument("--max-age-days", type=int, default=14, help="Skip refresh if manifest is newer than this many days unless --force.")
    parser.add_argument("--force", action="store_true", help="Refresh even if the manifest is still fresh.")
    parser.add_argument("--dry-run", action="store_true", help="Call FMP and print counts without writing files.")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    if not args.force and not args.dry_run and manifest_is_fresh(manifest_path, args.max_age_days):
        print(f"universe is fresh; skip refresh. manifest={manifest_path}")
        return

    criteria = UniverseCriteria(
        country=args.country.upper(),
        exchanges=tuple(item.strip().upper() for item in args.exchanges.split(",") if item.strip()),
        min_market_cap=args.min_market_cap,
        min_volume=args.min_volume,
        min_dollar_volume=args.min_dollar_volume,
        min_price=args.min_price,
        max_symbols=args.max_symbols,
    )

    settings = get_settings()
    print(f"fmp_rate_limit_per_minute={settings.fmp_rate_limit_per_minute}")
    raw_rows = fetch_company_screener(
        page_size=args.limit,
        criteria=criteria,
        target_symbols=args.target_symbols,
        max_pages=args.max_pages,
        max_page_errors=args.max_page_errors,
        failed_page_retry_rounds=args.failed_page_retry_rounds,
        timeout_seconds=args.screener_timeout_seconds,
        max_retries=args.screener_max_retries,
    )
    accepted, rejected = build_universe(raw_rows, criteria)
    validation_method = "none" if args.skip_price_validation else args.validation_method
    validation_date = date_from_text(args.price_validation_date) if args.price_validation_date else previous_new_york_business_day()
    if validation_method == "batch-quote":
        validation_client = FmpClient(timeout_seconds=args.validation_timeout_seconds, max_retries=args.validation_max_retries)
        accepted, quote_rejected = validate_batch_quotes(accepted, validation_client, args.quote_chunk_size)
        rejected.extend(quote_rejected)
    elif validation_method == "daily-bar":
        validation_client = FmpClient(timeout_seconds=args.validation_timeout_seconds, max_retries=args.validation_max_retries)
        accepted, price_rejected = validate_price_bars(accepted, validation_date, client=validation_client)
        rejected.extend(price_rejected)

    if criteria.max_symbols > 0:
        overflow = accepted[criteria.max_symbols :]
        accepted = accepted[: criteria.max_symbols]
        rejected.extend(row_with_reason(row, "max_symbols_overflow") for row in overflow)

    reason_counts = Counter(reason for row in rejected for reason in row.reason.split(";") if reason)
    print(f"raw_rows={len(raw_rows)} accepted={len(accepted)} rejected={len(rejected)}")
    print(f"validation_method={validation_method}")
    if validation_method == "daily-bar":
        print(f"price_validation_date={validation_date}")
    print(f"top_reject_reasons={dict(reason_counts.most_common(10))}")
    print(f"preview_symbols={','.join(row.symbol for row in accepted[:25])}")
    if len(accepted) < args.min_accepted and not args.allow_small_universe:
        raise SystemExit(
            f"accepted universe too small ({len(accepted)} < {args.min_accepted}); "
            "not writing outputs. Retry later or use --allow-small-universe."
        )
    if args.dry_run:
        return

    write_outputs(
        accepted=accepted,
        rejected=rejected,
        criteria=criteria,
        symbols_path=Path(args.output_symbols),
        accepted_csv_path=Path(args.output_csv),
        rejected_csv_path=Path(args.rejected_csv),
        manifest_path=manifest_path,
        raw_count=len(raw_rows),
        reason_counts=reason_counts,
        validation_method=validation_method,
        price_validation_date=validation_date if validation_method == "daily-bar" else None,
        target_symbols=args.target_symbols,
        min_accepted=args.min_accepted,
    )


def fetch_company_screener(
    page_size: int,
    criteria: UniverseCriteria,
    target_symbols: int,
    max_pages: int,
    max_page_errors: int,
    failed_page_retry_rounds: int,
    timeout_seconds: int,
    max_retries: int,
) -> list[dict[str, Any]]:
    if page_size <= 0:
        raise SystemExit("--limit must be positive")
    client = FmpClient(timeout_seconds=timeout_seconds, max_retries=max_retries)
    rows: list[dict[str, Any]] = []
    errors = 0
    stop_buffer = min(100, max(25, target_symbols // 40))
    exhausted_exchanges: set[str] = set()
    failed_pages: list[tuple[str, int]] = []
    last_preaccepted = 0
    for page in range(max_pages):
        progressed = False
        for exchange in criteria.exchanges:
            if exchange in exhausted_exchanges:
                continue
            params = screener_params(page_size, criteria, exchange=exchange)
            params["page"] = str(page)
            try:
                data, _ = client.get_json("/stable/company-screener", params)
                if not isinstance(data, list):
                    raise RuntimeError(f"Unexpected company-screener payload: {type(data).__name__}")
                page_rows = [row for row in data if isinstance(row, dict)]
                if not page_rows:
                    exhausted_exchanges.add(exchange)
                    print(f"screener exchange={exchange} page={page} rows=0 stop=true")
                    continue
                progressed = True
                rows.extend(page_rows)
                deduped = dedupe_raw_rows(rows)
                accepted, _ = build_universe(deduped, criteria)
                last_preaccepted = len(accepted)
                print(f"screener exchange={exchange} page={page} rows={len(page_rows)} raw={len(deduped)} preaccepted={last_preaccepted}")
                if last_preaccepted >= target_symbols + stop_buffer:
                    break
            except Exception as exc:
                errors += 1
                failed_pages.append((exchange, page))
                print(f"screener exchange={exchange} page={page} failed: {type(exc).__name__}")
                if errors >= max_page_errors:
                    break
        if errors >= max_page_errors:
            break
        if last_preaccepted >= target_symbols + stop_buffer:
            break
        if not progressed and len(exhausted_exchanges) == len(criteria.exchanges):
            break
    if failed_pages and failed_page_retry_rounds > 0:
        rows, last_preaccepted = retry_failed_screener_pages(
            client=client,
            page_size=page_size,
            criteria=criteria,
            rows=rows,
            failed_pages=failed_pages,
            retry_rounds=failed_page_retry_rounds,
        )
    output = dedupe_raw_rows(rows)
    if not output:
        raise SystemExit("company-screener returned no usable rows")
    return output


def retry_failed_screener_pages(
    client: FmpClient,
    page_size: int,
    criteria: UniverseCriteria,
    rows: list[dict[str, Any]],
    failed_pages: list[tuple[str, int]],
    retry_rounds: int,
) -> tuple[list[dict[str, Any]], int]:
    pending = sorted(set(failed_pages), key=lambda item: (item[1], item[0]))
    last_preaccepted = 0
    for retry_round in range(1, retry_rounds + 1):
        if not pending:
            break
        time.sleep(min(5, 2 + retry_round))
        print(f"retrying failed screener pages round={retry_round} count={len(pending)}")
        next_pending: list[tuple[str, int]] = []
        for exchange, page in pending:
            params = screener_params(page_size, criteria, exchange=exchange)
            params["page"] = str(page)
            try:
                data, _ = client.get_json("/stable/company-screener", params)
                if not isinstance(data, list):
                    raise RuntimeError(f"Unexpected company-screener payload: {type(data).__name__}")
                page_rows = [row for row in data if isinstance(row, dict)]
                rows.extend(page_rows)
                deduped = dedupe_raw_rows(rows)
                accepted, _ = build_universe(deduped, criteria)
                last_preaccepted = len(accepted)
                print(f"screener retry exchange={exchange} page={page} rows={len(page_rows)} raw={len(deduped)} preaccepted={last_preaccepted}")
            except Exception as exc:
                next_pending.append((exchange, page))
                print(f"screener retry exchange={exchange} page={page} failed: {type(exc).__name__}")
        pending = next_pending
    if pending:
        print(f"screener failed pages remaining={len(pending)}")
    return dedupe_raw_rows(rows), last_preaccepted


def screener_params(limit: int, criteria: UniverseCriteria, exchange: str = "") -> dict[str, str]:
    params = {
        "limit": str(limit),
        "isEtf": "false",
        "isFund": "false",
        "isActivelyTrading": "true",
        "marketCapMoreThan": str(int(criteria.min_market_cap)),
        "volumeMoreThan": str(int(criteria.min_volume)),
    }
    if criteria.country:
        params["country"] = criteria.country
    if exchange:
        params["exchange"] = exchange
    return params


def dedupe_raw_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for row in rows:
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        output.append(row)
    return output


def validate_price_bars(rows: list[UniverseRow], trade_date, client: FmpClient | None = None) -> tuple[list[UniverseRow], list[UniverseRow]]:
    client = client or FmpClient()
    accepted: list[UniverseRow] = []
    rejected: list[UniverseRow] = []
    for index, row in enumerate(rows, start=1):
        if index == 1 or index % 100 == 0 or index == len(rows):
            print(f"validating daily bars {index}/{len(rows)}")
        ok, reason = has_price_bar(client, row.symbol, trade_date)
        if ok:
            accepted.append(row)
        else:
            rejected.append(row_with_reason(row, reason))
    return accepted, rejected


def validate_batch_quotes(rows: list[UniverseRow], client: FmpClient | None = None, chunk_size: int = 100) -> tuple[list[UniverseRow], list[UniverseRow]]:
    if chunk_size <= 0:
        raise SystemExit("--quote-chunk-size must be positive")
    client = client or FmpClient()
    accepted: list[UniverseRow] = []
    rejected: list[UniverseRow] = []
    for index in range(0, len(rows), chunk_size):
        chunk = rows[index : index + chunk_size]
        print(f"validating batch quotes {index + 1}-{index + len(chunk)}/{len(rows)}")
        quoted, reason = get_batch_quote_symbols(client, [row.symbol for row in chunk])
        if reason:
            rejected.extend(row_with_reason(row, reason) for row in chunk)
            continue
        for row in chunk:
            if row.symbol in quoted:
                accepted.append(row)
            else:
                rejected.append(row_with_reason(row, "no_batch_quote"))
    return accepted, rejected


def get_batch_quote_symbols(client: FmpClient, symbols: list[str]) -> tuple[set[str], str]:
    try:
        data, _ = client.get_json("/stable/batch-quote", {"symbols": ",".join(symbols)})
    except Exception as exc:
        return set(), f"batch_quote_error:{type(exc).__name__}"
    if not isinstance(data, list):
        return set(), "batch_quote_payload"
    output: set[str] = set()
    for row in data:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        if row.get("price") in {None, ""} or row.get("volume") in {None, ""}:
            continue
        output.add(symbol)
    return output, ""


def has_price_bar(client: FmpClient, symbol: str, trade_date) -> tuple[bool, str]:
    try:
        data, _ = client.get_json(
            "/stable/historical-price-eod/full",
            {"symbol": symbol, "from": str(trade_date), "to": str(trade_date)},
        )
    except Exception as exc:
        return False, f"price_bar_error:{type(exc).__name__}"
    rows = data if isinstance(data, list) else data.get("historical", []) if isinstance(data, dict) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("date")) != str(trade_date):
            continue
        if row.get("close") in {None, ""} or row.get("volume") in {None, ""}:
            continue
        return True, ""
    return False, f"no_price_bar:{trade_date}"


def build_universe(raw_rows: list[dict[str, Any]], criteria: UniverseCriteria) -> tuple[list[UniverseRow], list[UniverseRow]]:
    accepted: list[UniverseRow] = []
    rejected: list[UniverseRow] = []
    seen: set[str] = set()
    for raw in raw_rows:
        row = parse_row(raw)
        reasons = reject_reasons(row, criteria)
        if row.symbol in seen:
            reasons.append("duplicate_symbol")
        if reasons:
            rejected.append(row_with_reason(row, ";".join(reasons)))
            continue
        seen.add(row.symbol)
        accepted.append(row)
    accepted.sort(key=lambda row: row.market_cap or Decimal("0"), reverse=True)
    rejected.sort(key=lambda row: (row.reason, row.symbol))
    return accepted, rejected


def parse_row(raw: dict[str, Any]) -> UniverseRow:
    symbol = str(raw.get("symbol") or "").strip().upper()
    company_name = str(raw.get("companyName") or raw.get("company_name") or "").strip()
    market_cap = decimal_or_none(raw.get("marketCap"))
    price = decimal_or_none(raw.get("price"))
    volume = decimal_or_none(raw.get("volume"))
    dollar_volume = price * volume if price is not None and volume is not None else None
    return UniverseRow(
        symbol=symbol,
        company_name=company_name,
        market_cap=market_cap,
        price=price,
        volume=volume,
        dollar_volume=dollar_volume,
        exchange=str(raw.get("exchange") or "").strip(),
        exchange_short_name=str(raw.get("exchangeShortName") or raw.get("exchange_short_name") or "").strip().upper(),
        country=str(raw.get("country") or "").strip().upper(),
        sector=str(raw.get("sector") or "").strip(),
        industry=str(raw.get("industry") or "").strip(),
        is_etf=bool_or_none(raw.get("isEtf")),
        is_fund=bool_or_none(raw.get("isFund")),
        is_actively_trading=bool_or_none(raw.get("isActivelyTrading")),
    )


def reject_reasons(row: UniverseRow, criteria: UniverseCriteria) -> list[str]:
    reasons: list[str] = []
    if not row.symbol:
        reasons.append("missing_symbol")
    if criteria.country and row.country != criteria.country:
        reasons.append("country")
    if row.exchange_short_name not in criteria.exchanges:
        reasons.append("exchange")
    if row.is_etf is True:
        reasons.append("etf")
    if row.is_fund is True:
        reasons.append("fund")
    if row.is_actively_trading is False:
        reasons.append("inactive")
    if row.symbol in EXCLUDED_SYMBOLS:
        reasons.append("excluded_symbol")
    if is_excluded_private_or_pseudo_public_name(row.company_name):
        reasons.append("excluded_name")
    if row.market_cap is None or row.market_cap < criteria.min_market_cap:
        reasons.append("market_cap")
    if row.volume is None or row.volume < criteria.min_volume:
        reasons.append("volume")
    if row.price is None or row.price < criteria.min_price:
        reasons.append("price")
    if row.dollar_volume is None or row.dollar_volume < criteria.min_dollar_volume:
        reasons.append("dollar_volume")
    if is_derivative_symbol(row.symbol):
        reasons.append("derivative_symbol")
    if is_derivative_or_fund_name(row.company_name):
        reasons.append("derivative_or_fund_name")
    if row.industry.strip().lower() == "shell companies":
        reasons.append("shell_company")
    return reasons


def is_derivative_symbol(symbol: str) -> bool:
    if not symbol:
        return True
    if any(char in symbol for char in ["/", "^"]):
        return True
    parts = re.split(r"[-.]", symbol)
    if len(parts) > 1 and parts[-1].upper() in BAD_SYMBOL_SUFFIXES:
        return True
    return False


def is_derivative_or_fund_name(name: str) -> bool:
    return any(pattern.search(name) for pattern in BAD_NAME_PATTERNS)


def is_excluded_private_or_pseudo_public_name(name: str) -> bool:
    return any(pattern.search(name) for pattern in EXCLUDED_NAME_PATTERNS)


def row_with_reason(row: UniverseRow, reason: str) -> UniverseRow:
    return UniverseRow(**{**asdict(row), "reason": reason})


def write_outputs(
    accepted: list[UniverseRow],
    rejected: list[UniverseRow],
    criteria: UniverseCriteria,
    symbols_path: Path,
    accepted_csv_path: Path,
    rejected_csv_path: Path,
    manifest_path: Path,
    raw_count: int,
    reason_counts: Counter[str],
    validation_method: str,
    price_validation_date,
    target_symbols: int,
    min_accepted: int,
) -> None:
    generated_at = datetime.now(tz=UTC).isoformat()
    for path in [symbols_path, accepted_csv_path, rejected_csv_path, manifest_path]:
        path.parent.mkdir(parents=True, exist_ok=True)

    symbols_lines = [
        f"# Generated by scripts/refresh_fmp_universe.py at {generated_at}",
        f"# Criteria: country={criteria.country}, exchanges={','.join(criteria.exchanges)}, "
        f"min_market_cap={criteria.min_market_cap}, min_volume={criteria.min_volume}, "
        f"min_dollar_volume={criteria.min_dollar_volume}, min_price={criteria.min_price}",
        "# Refresh cadence: every 14 days.",
    ]
    symbols_lines.extend(row.symbol for row in accepted)
    symbols_path.write_text("\n".join(symbols_lines) + "\n", encoding="utf-8")
    write_csv(accepted_csv_path, accepted)
    write_csv(rejected_csv_path, rejected)
    manifest_path.write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                "source": "fmp:/stable/company-screener",
                "refresh_cadence_days": 14,
                "raw_count": raw_count,
                "target_symbols": target_symbols,
                "accepted_count": len(accepted),
                "rejected_count": len(rejected),
                "criteria": {
                    "country": criteria.country,
                    "exchanges": list(criteria.exchanges),
                    "min_market_cap": str(criteria.min_market_cap),
                    "min_volume": str(criteria.min_volume),
                    "min_dollar_volume": str(criteria.min_dollar_volume),
                    "min_price": str(criteria.min_price),
                    "max_symbols": criteria.max_symbols,
                },
                "validation_method": validation_method,
                "price_validation_date": str(price_validation_date) if price_validation_date else None,
                "top_reject_reasons": dict(reason_counts.most_common(20)),
                "min_accepted": min_accepted,
                "outputs": {
                    "symbols": str(symbols_path),
                    "accepted_csv": str(accepted_csv_path),
                    "rejected_csv": str(rejected_csv_path),
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {symbols_path}")
    print(f"wrote {accepted_csv_path}")
    print(f"wrote {rejected_csv_path}")
    print(f"wrote {manifest_path}")


def write_csv(path: Path, rows: list[UniverseRow]) -> None:
    fieldnames = [
        "symbol",
        "company_name",
        "market_cap",
        "price",
        "volume",
        "dollar_volume",
        "exchange",
        "exchange_short_name",
        "country",
        "sector",
        "industry",
        "is_etf",
        "is_fund",
        "is_actively_trading",
        "reason",
    ]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: stringify_csv_value(value) for key, value in asdict(row).items()})


def manifest_is_fresh(path: Path, max_age_days: int) -> bool:
    if max_age_days <= 0 or not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        generated_at = datetime.fromisoformat(str(data["generated_at"]).replace("Z", "+00:00"))
    except Exception:
        return False
    return datetime.now(tz=UTC) - generated_at <= timedelta(days=max_age_days)


def previous_new_york_business_day(now: datetime | None = None):
    current = (now or datetime.now(tz=UTC)).astimezone(NY_TZ)
    candidate = current.date()
    if current.time() < datetime_time(16, 30):
        candidate -= timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def date_from_text(value: str):
    from datetime import date

    return date.fromisoformat(value)


def decimal_or_none(value: Any) -> Decimal | None:
    if value in {None, ""}:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def bool_or_none(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def stringify_csv_value(value: Any) -> str:
    if isinstance(value, Decimal):
        return format(value, "f")
    if value is None:
        return ""
    return str(value)


if __name__ == "__main__":
    main()
