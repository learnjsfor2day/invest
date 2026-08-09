#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


DEFAULT_INPUT_CSV = Path("data/universe/daily_universe.csv")
DEFAULT_OUTPUT_CSV = Path("data/universe/core_universe.csv")
DEFAULT_OUTPUT_SYMBOLS = Path("data/universe/core_symbols.txt")
DEFAULT_REJECTED_CSV = Path("data/universe/core_universe_excluded.csv")
DEFAULT_MANIFEST = Path("data/universe/core_manifest.json")
DEFAULT_EXCHANGES = ("NASDAQ", "NYSE", "AMEX")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the production core universe from the broader accepted universe.")
    parser.add_argument("--input-csv", default=str(DEFAULT_INPUT_CSV))
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT_CSV))
    parser.add_argument("--output-symbols", default=str(DEFAULT_OUTPUT_SYMBOLS))
    parser.add_argument("--rejected-csv", default=str(DEFAULT_REJECTED_CSV))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--size", type=int, default=1500)
    parser.add_argument("--country", default="US")
    parser.add_argument("--exchanges", default=",".join(DEFAULT_EXCHANGES))
    parser.add_argument("--min-price", default="1")
    parser.add_argument("--min-market-cap", default="20000000")
    parser.add_argument("--min-volume", default="3000")
    parser.add_argument("--min-dollar-volume", default="20000")
    args = parser.parse_args()

    rows = read_rows(Path(args.input_csv))
    criteria = {
        "country": args.country.upper(),
        "exchanges": [item.strip().upper() for item in args.exchanges.split(",") if item.strip()],
        "min_price": decimal_or_zero(args.min_price),
        "min_market_cap": decimal_or_zero(args.min_market_cap),
        "min_volume": decimal_or_zero(args.min_volume),
        "min_dollar_volume": decimal_or_zero(args.min_dollar_volume),
        "size": args.size,
    }
    eligible: list[dict[str, str]] = []
    rejected: list[dict[str, str]] = []
    seen: set[str] = set()

    for row in rows:
        symbol = row.get("symbol", "").strip().upper()
        reasons = reject_reasons(row, criteria)
        if symbol in seen:
            reasons.append("duplicate_symbol")
        if reasons:
            rejected.append({**row, "core_reason": ";".join(reasons)})
            continue
        seen.add(symbol)
        eligible.append(row)

    eligible.sort(key=quality_rank, reverse=True)
    core = eligible[: args.size]
    overflow = eligible[args.size :]
    rejected.extend({**row, "core_reason": "outside_core_rank"} for row in overflow)

    write_csv(Path(args.output_csv), core)
    write_symbols(Path(args.output_symbols), core, criteria)
    write_csv(Path(args.rejected_csv), rejected, extra_fields=["core_reason"])
    write_manifest(Path(args.manifest), rows, eligible, core, rejected, criteria, args)

    print(f"input_rows={len(rows)} eligible={len(eligible)} core={len(core)} rejected={len(rejected)}")
    print(f"preview={','.join(row['symbol'] for row in core[:25])}")
    print(f"wrote {args.output_symbols}")
    print(f"wrote {args.output_csv}")
    print(f"wrote {args.rejected_csv}")
    print(f"wrote {args.manifest}")
    if len(core) < args.size:
        raise SystemExit(f"core universe too small ({len(core)} < {args.size})")


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as file:
        return [{key: value for key, value in row.items()} for row in csv.DictReader(file)]


def reject_reasons(row: dict[str, str], criteria: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    symbol = row.get("symbol", "").strip().upper()
    if not symbol:
        reasons.append("missing_symbol")
    if criteria["country"] and row.get("country", "").strip().upper() != criteria["country"]:
        reasons.append("non_us_company")
    if row.get("exchange_short_name", "").strip().upper() not in criteria["exchanges"]:
        reasons.append("exchange")
    if bool_text(row.get("is_etf")) is True:
        reasons.append("etf")
    if bool_text(row.get("is_fund")) is True:
        reasons.append("fund")
    if bool_text(row.get("is_actively_trading")) is False:
        reasons.append("inactive")
    if decimal_or_zero(row.get("price")) < criteria["min_price"]:
        reasons.append("price")
    if decimal_or_zero(row.get("market_cap")) < criteria["min_market_cap"]:
        reasons.append("market_cap")
    if decimal_or_zero(row.get("volume")) < criteria["min_volume"]:
        reasons.append("volume")
    if decimal_or_zero(row.get("dollar_volume")) < criteria["min_dollar_volume"]:
        reasons.append("dollar_volume")
    return reasons


def quality_rank(row: dict[str, str]) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    return (
        decimal_or_zero(row.get("market_cap")),
        decimal_or_zero(row.get("dollar_volume")),
        decimal_or_zero(row.get("volume")),
        decimal_or_zero(row.get("price")),
    )


def write_symbols(path: Path, rows: list[dict[str, str]], criteria: dict[str, Any]) -> None:
    generated_at = datetime.now(tz=UTC).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Generated by scripts/build_core_universe.py at {generated_at}",
        f"# Core size: {criteria['size']}",
        f"# Criteria: country={criteria['country']}, exchanges={','.join(criteria['exchanges'])}, "
        f"min_market_cap={criteria['min_market_cap']}, min_volume={criteria['min_volume']}, "
        f"min_dollar_volume={criteria['min_dollar_volume']}, min_price={criteria['min_price']}",
        "# Sorted by market_cap, dollar_volume, volume, price.",
    ]
    lines.extend(row["symbol"].strip().upper() for row in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, str]], extra_fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
        *(extra_fields or []),
    ]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def write_manifest(
    path: Path,
    rows: list[dict[str, str]],
    eligible: list[dict[str, str]],
    core: list[dict[str, str]],
    rejected: list[dict[str, str]],
    criteria: dict[str, Any],
    args,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(tz=UTC).isoformat(),
                "source": str(args.input_csv),
                "input_count": len(rows),
                "eligible_count": len(eligible),
                "core_count": len(core),
                "rejected_count": len(rejected),
                "criteria": {key: str(value) if isinstance(value, Decimal) else value for key, value in criteria.items()},
                "outputs": {
                    "symbols": str(args.output_symbols),
                    "core_csv": str(args.output_csv),
                    "rejected_csv": str(args.rejected_csv),
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def decimal_or_zero(value: Any) -> Decimal:
    if value in {None, ""}:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def bool_text(value: Any) -> bool | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


if __name__ == "__main__":
    main()
