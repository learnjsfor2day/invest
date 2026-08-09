#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass

from sqlalchemy import text

from pit_radar.db.session import create_db_engine


@dataclass(frozen=True)
class DedupeRule:
    table: str
    pk: str
    group_by: tuple[str, ...]


DEDUPE_RULES = {
    "daily_market_bar": DedupeRule("pit.daily_market_bar", "daily_bar_id", ("security_id", "trade_date", "data_hash")),
    "estimate_snapshot": DedupeRule(
        "pit.estimate_snapshot",
        "estimate_id",
        ("security_id", "fiscal_period_end", "period_type", "data_hash"),
    ),
    "analyst_snapshot": DedupeRule("pit.analyst_snapshot", "analyst_snapshot_id", ("security_id", "data_hash")),
    "earnings_calendar_snapshot": DedupeRule(
        "pit.earnings_calendar_snapshot",
        "earnings_snapshot_id",
        ("security_id", "fiscal_period_end", "data_hash"),
    ),
    "financial_fact_snapshot": DedupeRule(
        "pit.financial_fact_snapshot",
        "financial_fact_id",
        ("security_id", "dataset_code", "period_type", "fiscal_period_end", "data_hash"),
    ),
    "metric_observation": DedupeRule(
        "pit.metric_observation",
        "observation_id",
        ("security_id", "metric_code", "period_end", "data_hash"),
    ),
    "news_item_snapshot": DedupeRule(
        "pit.news_item_snapshot",
        "news_snapshot_id",
        ("security_id", "news_type", "published_at", "data_hash"),
    ),
    "sec_filing_snapshot": DedupeRule(
        "pit.sec_filing_snapshot",
        "sec_filing_id",
        ("security_id", "form_type", "accepted_at", "data_hash"),
    ),
    "earning_transcript_snapshot": DedupeRule(
        "pit.earning_transcript_snapshot",
        "transcript_id",
        ("security_id", "fiscal_year", "fiscal_period", "data_hash"),
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove exact duplicate PIT snapshot rows while keeping the earliest fetched version.")
    parser.add_argument("--tables", default=",".join(DEDUPE_RULES), help="Comma-separated table names, or all.")
    parser.add_argument("--execute", action="store_true", help="Actually delete duplicates. Default is dry-run.")
    args = parser.parse_args()

    selected = list(DEDUPE_RULES) if args.tables.strip().lower() == "all" else [item.strip() for item in args.tables.split(",") if item.strip()]
    invalid = sorted(set(selected) - set(DEDUPE_RULES))
    if invalid:
        raise SystemExit(f"Unsupported tables: {','.join(invalid)}")

    engine = create_db_engine()
    with engine.begin() as conn:
        for name in selected:
            rule = DEDUPE_RULES[name]
            group_count = conn.scalar(text(_duplicate_group_count_sql(rule))) or 0
            duplicate_rows = conn.scalar(text(_duplicate_row_count_sql(rule))) or 0
            print(f"{name}: duplicate_groups={group_count} duplicate_rows={duplicate_rows}", flush=True)
            if args.execute and duplicate_rows:
                result = conn.execute(text(_delete_duplicates_sql(rule)))
                print(f"{name}: deleted_rows={result.rowcount}", flush=True)

    if not args.execute:
        print("dry_run=true; add --execute to delete exact duplicates.", flush=True)


def _duplicate_group_count_sql(rule: DedupeRule) -> str:
    group_cols = ", ".join(rule.group_by)
    return f"""
        SELECT COUNT(*) FROM (
            SELECT {group_cols}, COUNT(*) AS c
            FROM {rule.table}
            GROUP BY {group_cols}
            HAVING c > 1
        )
    """


def _duplicate_row_count_sql(rule: DedupeRule) -> str:
    group_cols = ", ".join(rule.group_by)
    return f"""
        SELECT COALESCE(SUM(c - 1), 0) FROM (
            SELECT {group_cols}, COUNT(*) AS c
            FROM {rule.table}
            GROUP BY {group_cols}
            HAVING c > 1
        )
    """


def _delete_duplicates_sql(rule: DedupeRule) -> str:
    partition_cols = ", ".join(rule.group_by)
    return f"""
        DELETE FROM {rule.table}
        WHERE {rule.pk} IN (
            SELECT {rule.pk}
            FROM (
                SELECT
                    {rule.pk},
                    ROW_NUMBER() OVER (
                        PARTITION BY {partition_cols}
                        ORDER BY fetched_at ASC, recorded_at ASC, {rule.pk} ASC
                    ) AS duplicate_rank
                FROM {rule.table}
            ) ranked
            WHERE duplicate_rank > 1
        )
    """


if __name__ == "__main__":
    main()
