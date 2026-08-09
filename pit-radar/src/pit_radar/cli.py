from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Annotated

import typer
from alembic import command
from alembic.config import Config

from pit_radar.collectors import (
    FmpDailyBarsCollector,
    FmpEarningsCollector,
    FmpEstimatesCollector,
    FmpFinancialsCollector,
    FmpMacroCalendarCollector,
    FmpNewsCollector,
    FmpSecFilingsCollector,
    FmpTranscriptsCollector,
    MockDailyBarsCollector,
    MockEarningsCollector,
    MockEstimatesCollector,
)
from pit_radar.collectors.base import CollectionContext
from pit_radar.config import get_settings
from pit_radar.db.session import create_session_factory
from pit_radar.services.asof import AsOfService
from pit_radar.services.dictionary import export_dictionary
from pit_radar.services.ingest import IngestService
from pit_radar.storage.local import LocalRawObjectStore
from pit_radar.time import parse_datetime, to_new_york, utc_now

app = typer.Typer(help="美股 Point-in-Time 数据库工具")
db_app = typer.Typer(help="数据库管理")
ingest_app = typer.Typer(help="数据采集")
query_app = typer.Typer(help="PIT 查询")
dictionary_app = typer.Typer(help="数据字典")
app.add_typer(db_app, name="db")
app.add_typer(ingest_app, name="ingest")
app.add_typer(query_app, name="query")
app.add_typer(dictionary_app, name="dictionary")


@db_app.command("upgrade")
def db_upgrade() -> None:
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    typer.echo("数据库已升级到最新版本。")


def _symbols(value: str | None) -> list[str]:
    settings = get_settings()
    raw = value or ",".join(settings.default_symbols)
    return [item.strip().upper() for item in raw.split(",") if item.strip()]


def _context(
    mode: str,
    symbols: str | None,
    from_date: date | None = None,
    to_date: date | None = None,
    fetched_at=None,
) -> CollectionContext:
    return CollectionContext(
        collection_mode=mode,
        symbols=_symbols(symbols),
        fetched_at=fetched_at or utc_now(),
        from_date=from_date,
        to_date=to_date,
    )


def _run_collector(collector, context: CollectionContext) -> None:
    _run_collectors([collector], context)


def _run_collectors(collectors, context: CollectionContext) -> None:
    settings = get_settings()
    session_factory = create_session_factory()
    with session_factory() as session:
        service = IngestService(session, LocalRawObjectStore(settings.raw_storage_root))
        runs = [service.ingest(collector, context) for collector in collectors]
        session.commit()
        for run in runs:
            typer.echo(
                f"{run.job_name}: run_id={run.run_id} status={run.status} success={run.success_count} "
                f"failed={run.failed_count} skipped={run.skipped_count}"
            )


@ingest_app.command("mock-estimates")
def ingest_mock_estimates(
    mode: Annotated[str, typer.Option(help="live/backfill/replay")] = "live",
    symbols: Annotated[str | None, typer.Option(help="逗号分隔ticker")] = None,
) -> None:
    _run_collector(MockEstimatesCollector(), _context(mode, symbols))


@ingest_app.command("mock-daily-bars")
def ingest_mock_daily_bars(
    mode: Annotated[str, typer.Option(help="live/backfill/replay")] = "live",
    symbols: Annotated[str | None, typer.Option(help="逗号分隔ticker")] = None,
    to_date: Annotated[str | None, typer.Option(help="交易日期 YYYY-MM-DD")] = None,
) -> None:
    _run_collector(MockDailyBarsCollector(), _context(mode, symbols, to_date=_parse_date(to_date)))


@ingest_app.command("mock-earnings")
def ingest_mock_earnings(
    mode: Annotated[str, typer.Option(help="live/backfill/replay")] = "live",
    symbols: Annotated[str | None, typer.Option(help="逗号分隔ticker")] = None,
) -> None:
    _run_collector(MockEarningsCollector(), _context(mode, symbols))


@ingest_app.command("fmp-estimates")
def ingest_fmp_estimates(
    mode: Annotated[str, typer.Option(help="live/backfill/replay")] = "live",
    symbols: Annotated[str | None, typer.Option(help="逗号分隔ticker")] = None,
) -> None:
    _run_collector(FmpEstimatesCollector(), _context(mode, symbols))


@ingest_app.command("fmp-daily-bars")
def ingest_fmp_daily_bars(
    mode: Annotated[str, typer.Option(help="live/backfill/replay")] = "live",
    symbols: Annotated[str | None, typer.Option(help="逗号分隔ticker")] = None,
    from_date: Annotated[str | None, typer.Option(help="开始日期 YYYY-MM-DD")] = None,
    to_date: Annotated[str | None, typer.Option(help="结束日期 YYYY-MM-DD")] = None,
    include_profile: Annotated[bool, typer.Option(help="是否顺带刷新公司profile；每日价格批量任务建议关闭")] = True,
) -> None:
    _run_collector(
        FmpDailyBarsCollector(include_profile=include_profile),
        _context(mode, symbols, from_date=_parse_date(from_date), to_date=_parse_date(to_date)),
    )


@ingest_app.command("fmp-earnings")
def ingest_fmp_earnings(
    mode: Annotated[str, typer.Option(help="live/backfill/replay")] = "live",
    symbols: Annotated[str | None, typer.Option(help="逗号分隔ticker")] = None,
) -> None:
    _run_collector(FmpEarningsCollector(), _context(mode, symbols))


@ingest_app.command("fmp-news")
def ingest_fmp_news(
    mode: Annotated[str, typer.Option(help="live/backfill/replay")] = "live",
    symbols: Annotated[str | None, typer.Option(help="逗号分隔ticker")] = None,
    limit: Annotated[int, typer.Option(help="每只股票最多新闻条数")] = 50,
    from_date: Annotated[str | None, typer.Option(help="新闻开始日期 YYYY-MM-DD")] = None,
    to_date: Annotated[str | None, typer.Option(help="新闻结束日期 YYYY-MM-DD")] = None,
) -> None:
    _run_collector(FmpNewsCollector(limit=limit), _context(mode, symbols, from_date=_parse_date(from_date), to_date=_parse_date(to_date)))


@ingest_app.command("fmp-financials")
def ingest_fmp_financials(
    mode: Annotated[str, typer.Option(help="live/backfill/replay")] = "live",
    symbols: Annotated[str | None, typer.Option(help="逗号分隔ticker")] = None,
    periods: Annotated[str, typer.Option(help="逗号分隔 period，例如 annual,quarter")] = "annual,quarter",
    limit: Annotated[int, typer.Option(help="每个period最多拉取行数")] = 8,
) -> None:
    _run_collector(FmpFinancialsCollector(periods=_periods(periods), limit=limit), _context(mode, symbols))


@ingest_app.command("fmp-sec-filings")
def ingest_fmp_sec_filings(
    mode: Annotated[str, typer.Option(help="live/backfill/replay")] = "live",
    symbols: Annotated[str | None, typer.Option(help="逗号分隔ticker")] = None,
    from_date: Annotated[str | None, typer.Option(help="开始日期 YYYY-MM-DD")] = None,
    to_date: Annotated[str | None, typer.Option(help="结束日期 YYYY-MM-DD")] = None,
    form_types: Annotated[str, typer.Option(help="逗号分隔SEC表格类型，例如 8-K,10-Q,10-K")] = "8-K",
    limit: Annotated[int, typer.Option(help="每只股票最多文件数")] = 100,
) -> None:
    _run_collector(
        FmpSecFilingsCollector(form_types=_form_types(form_types), limit=limit),
        _context(mode, symbols, from_date=_parse_date(from_date), to_date=_parse_date(to_date)),
    )


@ingest_app.command("fmp-transcripts")
def ingest_fmp_transcripts(
    mode: Annotated[str, typer.Option(help="live/backfill/replay")] = "live",
    symbols: Annotated[str | None, typer.Option(help="逗号分隔ticker")] = None,
    periods: Annotated[str, typer.Option(help="逗号分隔 year:quarter，例如 2025:4,2026:1")] = "",
) -> None:
    transcript_targets = _transcript_periods(periods)
    if not transcript_targets:
        raise typer.BadParameter("transcript periods are required, e.g. --periods 2025:4")
    _run_collector(FmpTranscriptsCollector(periods=transcript_targets), _context(mode, symbols))


@ingest_app.command("fmp-macro-calendar")
def ingest_fmp_macro_calendar(
    mode: Annotated[str, typer.Option(help="live/backfill/replay")] = "live",
    from_date: Annotated[str | None, typer.Option(help="开始日期 YYYY-MM-DD，默认今天")] = None,
    to_date: Annotated[str | None, typer.Option(help="结束日期 YYYY-MM-DD，默认开始日期+14天")] = None,
    countries: Annotated[str, typer.Option(help="逗号分隔国家/地区，例如 US,EU,UK；留空表示不过滤")] = "US",
) -> None:
    fetched_at = utc_now()
    start = _parse_date(from_date) or to_new_york(fetched_at).date()
    end = _parse_date(to_date) or start + timedelta(days=14)
    context = CollectionContext(
        collection_mode=mode,
        symbols=[item for item in _countries(countries)] or ["ALL"],
        fetched_at=fetched_at,
        from_date=start,
        to_date=end,
    )
    _run_collector(FmpMacroCalendarCollector(countries=_countries(countries)), context)


@ingest_app.command("daily-snapshot")
def ingest_daily_snapshot(
    mode: Annotated[str, typer.Option(help="live/backfill/replay")] = "live",
    symbols: Annotated[str | None, typer.Option(help="逗号分隔ticker")] = None,
    from_date: Annotated[str | None, typer.Option(help="日线开始日期 YYYY-MM-DD，默认等于结束日期")] = None,
    to_date: Annotated[str | None, typer.Option(help="日线结束日期 YYYY-MM-DD，默认今天")] = None,
    news_limit: Annotated[int, typer.Option(help="每只股票最多新闻条数")] = 50,
) -> None:
    fetched_at = utc_now()
    end = _parse_date(to_date) or to_new_york(fetched_at).date()
    start = _parse_date(from_date) or end
    context = _context(mode, symbols, from_date=start, to_date=end, fetched_at=fetched_at)
    _run_collectors(
        [
            FmpEstimatesCollector(),
            FmpDailyBarsCollector(),
            FmpEarningsCollector(),
            FmpNewsCollector(limit=news_limit),
            FmpSecFilingsCollector(form_types=("8-K",), limit=50),
        ],
        context,
    )


@ingest_app.command("earnings-event-snapshot")
def ingest_earnings_event_snapshot(
    mode: Annotated[str, typer.Option(help="live/backfill/replay")] = "live",
    symbols: Annotated[str | None, typer.Option(help="逗号分隔ticker")] = None,
    periods: Annotated[str, typer.Option(help="逗号分隔 period，例如 annual,quarter")] = "annual,quarter",
    financial_limit: Annotated[int, typer.Option(help="每个period最多拉取财务行数")] = 8,
    news_limit: Annotated[int, typer.Option(help="每只股票最多新闻条数")] = 50,
    filings_from: Annotated[str | None, typer.Option(help="SEC文件开始日期 YYYY-MM-DD")] = None,
    filings_to: Annotated[str | None, typer.Option(help="SEC文件结束日期 YYYY-MM-DD")] = None,
    transcript_periods: Annotated[str, typer.Option(help="可选，逗号分隔 year:quarter，例如 2025:4")] = "",
) -> None:
    fetched_at = utc_now()
    context = _context(mode, symbols, from_date=_parse_date(filings_from), to_date=_parse_date(filings_to), fetched_at=fetched_at)
    collectors = [
        FmpEarningsCollector(),
        FmpFinancialsCollector(periods=_periods(periods), limit=financial_limit),
        FmpNewsCollector(limit=news_limit),
        FmpSecFilingsCollector(form_types=("8-K", "10-Q", "10-K"), limit=100),
    ]
    transcript_targets = _transcript_periods(transcript_periods)
    if transcript_targets:
        collectors.append(FmpTranscriptsCollector(periods=transcript_targets))
    _run_collectors(collectors, context)


@query_app.command("estimates-as-of")
def query_estimates_as_of(
    ticker: Annotated[str, typer.Option(help="ticker，例如 MU")],
    cutoff: Annotated[str, typer.Option(help="ISO时间，例如 2026-07-14T09:30:00-04:00")],
    strict_live: Annotated[bool, typer.Option(help="只使用 live 数据")] = True,
) -> None:
    cutoff_time = parse_datetime(cutoff)
    session_factory = create_session_factory()
    with session_factory() as session:
        service = AsOfService(session)
        security_id = service.resolve_security_id(ticker, cutoff_time)
        if security_id is None:
            typer.echo("暂无数据")
            return
        rows = service.get_estimates_as_of([security_id], cutoff_time, strict_live=strict_live)
        typer.echo(_json_rows(rows))


@query_app.command("earnings-as-of")
def query_earnings_as_of(
    ticker: Annotated[str, typer.Option(help="ticker，例如 MU")],
    cutoff: Annotated[str, typer.Option(help="ISO时间，例如 2026-07-14T09:30:00-04:00")],
    strict_live: Annotated[bool, typer.Option(help="只使用 live 数据")] = True,
) -> None:
    cutoff_time = parse_datetime(cutoff)
    session_factory = create_session_factory()
    with session_factory() as session:
        service = AsOfService(session)
        security_id = service.resolve_security_id(ticker, cutoff_time)
        if security_id is None:
            typer.echo("暂无数据")
            return
        rows = service.get_earnings_calendar_as_of([security_id], cutoff_time, strict_live=strict_live)
        typer.echo(_json_rows(rows))


@dictionary_app.command("export")
def dictionary_export(
    format: Annotated[str, typer.Option(help="markdown/csv")] = "markdown",
    output: Annotated[Path, typer.Option(help="输出文件")] = Path("DATA_DICTIONARY.md"),
) -> None:
    export_dictionary(output, format)
    typer.echo(f"已导出数据字典：{output}")


@app.command("ui")
def ui() -> None:
    import subprocess
    import sys

    app_path = Path(__file__).parent / "ui" / "app.py"
    raise typer.Exit(subprocess.call([sys.executable, "-m", "streamlit", "run", str(app_path)]))


def _json_rows(rows: list[object]) -> str:
    import json

    def encode(row):
        return {col.name: getattr(row, col.name) for col in row.__table__.columns}

    return json.dumps([encode(row) for row in rows], ensure_ascii=False, indent=2, default=str)


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _periods(value: str) -> tuple[str, ...]:
    periods = tuple(item.strip().lower() for item in value.split(",") if item.strip())
    return periods or ("annual", "quarter")


def _form_types(value: str) -> tuple[str, ...]:
    return tuple(item.strip().upper() for item in value.split(",") if item.strip())


def _countries(value: str) -> tuple[str, ...]:
    return tuple(item.strip().upper() for item in value.split(",") if item.strip())


def _transcript_periods(value: str) -> tuple[tuple[int, int], ...]:
    output: list[tuple[int, int]] = []
    for item in value.split(","):
        raw = item.strip().replace("Q", "").replace("q", "")
        if not raw:
            continue
        if ":" not in raw:
            raise typer.BadParameter("transcript periods must be year:quarter, e.g. 2025:4")
        year_text, quarter_text = raw.split(":", 1)
        output.append((int(year_text), int(quarter_text)))
    return tuple(output)
