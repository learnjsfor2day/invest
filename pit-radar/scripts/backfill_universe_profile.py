#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import select

from pit_radar.config import get_settings
from pit_radar.db.models import DataSource, IngestRun, MetricDefinition, MetricObservation, RawPayload, Security, SecurityIdentifier
from pit_radar.db.session import create_session_factory
from pit_radar.storage.local import LocalRawObjectStore
from pit_radar.time import ensure_utc, utc_now


DEFAULT_UNIVERSE_CSV = Path("data/universe/core_universe.csv")
DEFAULT_MANIFEST = Path("data/universe/core_manifest.json")

METRIC_DEFINITIONS = {
    "market_cap": ("市值", "来自股票池刷新结果的公司市值。", "USD"),
    "profile_price": ("最新价格", "来自股票池刷新结果的最新价格。", "USD"),
    "average_volume": ("成交量", "来自股票池刷新结果的成交量字段。", "shares"),
    "dollar_volume": ("成交额", "来自股票池刷新结果的 price * volume。", "USD"),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill company basics and snapshot metrics from the core universe CSV.")
    parser.add_argument("--universe-csv", default=str(DEFAULT_UNIVERSE_CSV))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--mode", default="live", choices=["live", "backfill", "replay"])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    universe_path = Path(args.universe_csv)
    manifest_path = Path(args.manifest)
    rows = load_universe_rows(universe_path)
    fetched_at = manifest_generated_at(manifest_path) or utc_now()
    print(f"universe_csv={universe_path}", flush=True)
    print(f"rows={len(rows)} fetched_at={fetched_at.isoformat()}", flush=True)
    if args.dry_run:
        print(f"dry_run=true preview={','.join(row['symbol'] for row in rows[:20])}", flush=True)
        return

    settings = get_settings()
    session_factory = create_session_factory()
    store = LocalRawObjectStore(settings.raw_storage_root)
    with session_factory() as session:
        source = get_or_create_source(session)
        run = IngestRun(
            job_name="local:universe_profile",
            dataset_code="universe_profile",
            source_id=source.source_id,
            collection_mode=args.mode,
            scheduled_at=fetched_at,
            started_at=utc_now(),
            status="running",
            requested_count=len(rows),
            metadata_json={"universe_csv": str(universe_path), "manifest": str(manifest_path)},
        )
        session.add(run)
        session.flush()
        payload = get_or_create_payload(session, store, run, source, rows, fetched_at, universe_path, manifest_path)
        ensure_metric_definitions(session)

        updated_securities = 0
        inserted_metrics = 0
        skipped_metrics = 0
        for row in rows:
            security, changed = upsert_security(session, source.source_id, row, fetched_at)
            updated_securities += int(changed)
            inserted, skipped = insert_metrics(session, source.source_id, payload.payload_id, security, row, fetched_at)
            inserted_metrics += inserted
            skipped_metrics += skipped

        run.success_count = updated_securities
        run.skipped_count = skipped_metrics
        run.finished_at = utc_now()
        run.status = "success"
        metadata = dict(run.metadata_json or {})
        metadata.update(
            {
                "updated_securities": updated_securities,
                "inserted_metrics": inserted_metrics,
                "skipped_metrics": skipped_metrics,
            }
        )
        run.metadata_json = metadata
        session.commit()

    print(
        f"done updated_securities={updated_securities} inserted_metrics={inserted_metrics} "
        f"skipped_metrics={skipped_metrics}",
        flush=True,
    )


def load_universe_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise SystemExit(f"{path} not found")
    with path.open("r", encoding="utf-8", newline="") as file:
        rows = [
            {key: (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(file)
            if (row.get("symbol") or "").strip()
        ]
    rows.sort(key=lambda row: row["symbol"])
    return rows


def manifest_generated_at(path: Path) -> datetime | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return ensure_utc(datetime.fromisoformat(str(data["generated_at"]).replace("Z", "+00:00")))
    except Exception:
        return None


def get_or_create_source(session) -> DataSource:
    source = session.scalar(select(DataSource).where(DataSource.source_code == "fmp_universe"))
    if source:
        return source
    source = DataSource(
        source_code="fmp_universe",
        source_name="FMP Core Universe Snapshot",
        source_type="derived_file",
        base_url="data/universe/core_universe.csv",
        timezone="UTC",
    )
    session.add(source)
    session.flush()
    return source


def get_or_create_payload(
    session,
    store: LocalRawObjectStore,
    run: IngestRun,
    source: DataSource,
    rows: list[dict[str, str]],
    fetched_at: datetime,
    universe_path: Path,
    manifest_path: Path,
) -> RawPayload:
    raw = {
        "universe_csv": str(universe_path),
        "manifest": str(manifest_path),
        "row_count": len(rows),
        "rows": rows,
    }
    raw_bytes = json.dumps(raw, ensure_ascii=False, sort_keys=True).encode("utf-8")
    content_hash = hashlib.sha256(raw_bytes).hexdigest()
    request_key = f"universe-profile:{fetched_at.isoformat()}"
    existing = session.scalar(
        select(RawPayload).where(
            RawPayload.source_id == source.source_id,
            RawPayload.dataset_code == "universe_profile",
            RawPayload.request_key == request_key,
            RawPayload.fetched_at == fetched_at,
            RawPayload.content_hash == content_hash,
        )
    )
    if existing:
        return existing
    object_uri = store.put_bytes(
        f"universe_profile/{source.source_code}/{fetched_at.year:04d}/{fetched_at.month:02d}/{fetched_at.day:02d}/{content_hash}.json.gz",
        gzip.compress(raw_bytes),
    )
    payload = RawPayload(
        run_id=run.run_id,
        source_id=source.source_id,
        dataset_code="universe_profile",
        request_key=request_key,
        source_published_at=fetched_at,
        fetched_at=fetched_at,
        content_hash=content_hash,
        object_uri=object_uri,
        http_status=None,
        metadata_json={"row_count": len(rows)},
    )
    session.add(payload)
    session.flush()
    return payload


def ensure_metric_definitions(session) -> None:
    for metric_code, (name, description, unit) in METRIC_DEFINITIONS.items():
        if session.get(MetricDefinition, metric_code):
            continue
        session.add(
            MetricDefinition(
                metric_code=metric_code,
                display_name_zh=name,
                description_zh=description,
                value_type="numeric",
                unit=unit,
                frequency="snapshot",
            )
        )
    session.flush()


def upsert_security(session, source_id: int, row: dict[str, str], observed_at: datetime) -> tuple[Security, bool]:
    symbol = row["symbol"].upper()
    security = session.scalar(select(Security).where(Security.primary_ticker == symbol))
    changed = False
    if security is None:
        security = Security(
            primary_ticker=symbol,
            company_name=row.get("company_name") or f"{symbol} Unknown",
            exchange=row.get("exchange_short_name") or row.get("exchange") or None,
            sector=row.get("sector") or None,
            industry=row.get("industry") or None,
            currency="USD",
            country=row.get("country") or "US",
            is_active=parse_bool(row.get("is_actively_trading")),
            first_seen_at=observed_at,
            last_seen_at=observed_at,
        )
        session.add(security)
        session.flush()
        changed = True
    else:
        updates = {
            "company_name": row.get("company_name") or security.company_name,
            "exchange": row.get("exchange_short_name") or row.get("exchange") or security.exchange,
            "sector": row.get("sector") or security.sector,
            "industry": row.get("industry") or security.industry,
            "currency": "USD",
            "country": row.get("country") or security.country,
            "is_active": parse_bool(row.get("is_actively_trading")),
        }
        for field, value in updates.items():
            if value is not None and getattr(security, field) != value:
                setattr(security, field, value)
                changed = True
        security.last_seen_at = observed_at

    ensure_ticker_identifier(session, security.security_id, symbol, source_id, observed_at)
    return security, changed


def ensure_ticker_identifier(session, security_id: int, symbol: str, source_id: int, observed_at: datetime) -> None:
    existing = session.scalar(
        select(SecurityIdentifier).where(
            SecurityIdentifier.security_id == security_id,
            SecurityIdentifier.identifier_type == "ticker",
            SecurityIdentifier.identifier_value == symbol,
            SecurityIdentifier.valid_to.is_(None),
        )
    )
    if existing:
        return
    session.add(
        SecurityIdentifier(
            security_id=security_id,
            identifier_type="ticker",
            identifier_value=symbol,
            valid_from=observed_at,
            source_id=source_id,
        )
    )


def insert_metrics(
    session,
    source_id: int,
    payload_id: int,
    security: Security,
    row: dict[str, str],
    fetched_at: datetime,
) -> tuple[int, int]:
    values = {
        "market_cap": decimal_or_none(row.get("market_cap")),
        "profile_price": decimal_or_none(row.get("price")),
        "average_volume": decimal_or_none(row.get("volume")),
        "dollar_volume": decimal_or_none(row.get("dollar_volume")),
    }
    inserted = 0
    skipped = 0
    period_end = fetched_at.date()
    for metric_code, value in values.items():
        if value is None:
            skipped += 1
            continue
        data_hash = hash_metric(security.primary_ticker, metric_code, value, period_end)
        exists = session.scalar(
            select(MetricObservation.observation_id).where(
                MetricObservation.security_id == security.security_id,
                MetricObservation.metric_code == metric_code,
                MetricObservation.period_end == period_end,
                MetricObservation.fetched_at == fetched_at,
                MetricObservation.data_hash == data_hash,
            )
        )
        if exists:
            skipped += 1
            continue
        session.add(
            MetricObservation(
                security_id=security.security_id,
                metric_code=metric_code,
                period_end=period_end,
                event_at=fetched_at,
                source_published_at=fetched_at,
                fetched_at=fetched_at,
                value_numeric=value,
                unit=METRIC_DEFINITIONS[metric_code][2],
                currency="USD" if metric_code in {"market_cap", "profile_price", "dollar_volume"} else None,
                source_id=source_id,
                raw_payload_id=payload_id,
                data_hash=data_hash,
                quality_flags={"source": "daily_universe_csv"},
            )
        )
        inserted += 1
    return inserted, skipped


def hash_metric(symbol: str, metric_code: str, value: Decimal, period_end) -> str:
    raw = json.dumps(
        {"symbol": symbol, "metric_code": metric_code, "value": str(value), "period_end": str(period_end)},
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def decimal_or_none(value: str | None) -> Decimal | None:
    if value in {None, ""}:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def parse_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() not in {"false", "0", "no", "n"}


if __name__ == "__main__":
    main()
