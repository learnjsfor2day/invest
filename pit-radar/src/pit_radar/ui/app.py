from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import desc, func, select

from pit_radar.db.models import (
    AnalystSnapshot,
    DailyMarketBar,
    EstimateSnapshot,
    EarningsCalendarSnapshot,
    EarningTranscriptSnapshot,
    FinancialFactSnapshot,
    MacroEventSnapshot,
    MetricObservation,
    NewsItemSnapshot,
    SecFilingSnapshot,
    Security,
    SecurityIdentifier,
    SourceDocumentSnapshot,
)
from pit_radar.db.models.raw import DatasetCoverage, IngestRun, RawPayload
from pit_radar.db.session import create_session_factory
from pit_radar.services.asof import AsOfService
from pit_radar.services.dictionary import rows as dictionary_rows
from pit_radar.time import ensure_utc, parse_datetime, to_new_york, utc_now
from pit_radar.ui.field_labels_zh import ENUM_LABELS_ZH


FINANCIAL_DATASET_LABELS = {
    "income_statement": "利润表",
    "balance_sheet": "资产负债表",
    "cash_flow": "现金流量表",
    "ratios": "财务比率",
    "key_metrics": "关键指标",
    "financial_growth": "增长指标",
    "financial_scores": "财务评分",
}

NEWS_TYPE_LABELS = {
    "stock_news": "股票新闻",
    "press_release": "公司公告",
}

DOCUMENT_TYPE_LABELS = {
    "stock_news": "股票新闻",
    "press_release": "公司公告",
    "sec_filing": "SEC文件",
    "earning_transcript": "电话会原文",
}

MACRO_IMPACT_LABELS = {
    "High": "高",
    "Medium": "中",
    "Low": "低",
}

MACRO_IMPACT_ORDER = {
    "High": 0,
    "Medium": 1,
    "Low": 2,
}

MACRO_WINDOW_OPTIONS = ["全部", "今天", "未来7天", "未来30天", "过去7天"]

PROJECT_ROOT = Path(__file__).resolve().parents[3]
LOG_DIR = PROJECT_ROOT / "logs"
TASK_HISTORY_FILE = LOG_DIR / "task_runs.jsonl"
TASK_SCHEDULE_FILE = PROJECT_ROOT / "config" / "task_schedule.json"
TASK_SCHEDULE_SYNC_SCRIPT = PROJECT_ROOT / "scripts" / "sync_launchd_schedule.py"
CORE_SYMBOLS_FILE = PROJECT_ROOT / "data" / "universe" / "core_symbols.txt"
INFLECTION_RADAR_DIR = PROJECT_ROOT / "data" / "inflection_radar"

SCHEDULED_TASKS = [
    {
        "name": "日线快照",
        "label": "com.aibao.pitradar.daily",
        "schedule": "每日 07:30 北京时间",
        "default_times": ("07:30",),
        "default_days": (),
        "status_patterns": ("daily_fmp_*.status",),
        "log_patterns": ("daily_fmp_*.log",),
    },
    {
        "name": "分析师预测",
        "label": "com.aibao.pitradar.estimates",
        "schedule": "每日 09:20 北京时间",
        "default_times": ("09:20",),
        "default_days": (),
        "status_patterns": ("estimates_snapshot.status",),
        "log_patterns": ("estimates_snapshot_*.log",),
    },
    {
        "name": "财报事件",
        "label": "com.aibao.pitradar.earnings",
        "schedule": "每日 08:10、22:10 北京时间",
        "default_times": ("08:10", "22:10"),
        "default_days": (),
        "status_patterns": ("earnings_events.status",),
        "log_patterns": ("earnings_events_*.log",),
    },
    {
        "name": "宏观日历",
        "label": "com.aibao.pitradar.macro",
        "schedule": "每日 07:05、20:40、22:10 北京时间",
        "default_times": ("07:05", "20:40", "22:10"),
        "default_days": (),
        "status_patterns": ("macro_calendar.status",),
        "log_patterns": ("macro_calendar_*.log",),
    },
    {
        "name": "宏观提醒",
        "label": "com.aibao.pitradar.macro-reminder",
        "schedule": "每日 07:20 北京时间",
        "default_times": ("07:20",),
        "default_days": (),
        "status_patterns": ("macro_reminder.status",),
        "log_patterns": ("macro_reminder_*.log",),
    },
    {
        "name": "股票池刷新",
        "label": "com.aibao.pitradar.universe",
        "schedule": "每月 1 日、15 日 08:30 北京时间",
        "default_times": ("08:30",),
        "default_days": (1, 15),
        "status_patterns": ("universe_refresh.status", "universe_profile_backfill.status"),
        "log_patterns": ("universe_refresh_*.log", "universe_profile_backfill_*.log"),
    },
    {
        "name": "基本面拐点雷达",
        "label": "com.aibao.pitradar.inflection-radar",
        "schedule": "每日 10:45 北京时间",
        "default_times": ("10:45",),
        "default_days": (),
        "status_patterns": ("inflection_radar.status",),
        "log_patterns": ("inflection_radar_*.log",),
    },
]

DATASET_ARCHITECTURE = [
    {
        "layer": "core",
        "table": "core.security",
        "model": Security,
        "latest_field": "updated_at",
        "purpose": "证券主数据、股票池主体、ticker 映射入口",
        "cadence": "半月刷新股票池，必要时补充公司资料",
        "pit_time": "first_seen_at / last_seen_at",
        "dedupe": "cik、security_id、历史 identifier",
        "runtime": "分钟级",
    },
    {
        "layer": "pit",
        "table": "pit.daily_market_bar",
        "model": DailyMarketBar,
        "latest_field": "fetched_at",
        "purpose": "日线 OHLCV，雷达回测的价格基准",
        "cadence": "每日美股收盘后抓前一交易日",
        "pit_time": "trade_date + fetched_at",
        "dedupe": "security_id + trade_date + data_hash",
        "runtime": "核心池约 10-15 分钟；补跑只跑缺口",
    },
    {
        "layer": "pit",
        "table": "pit.estimate_snapshot",
        "model": EstimateSnapshot,
        "latest_field": "fetched_at",
        "purpose": "未来季度/年度 EPS 与营收共识预期",
        "cadence": "每日一次；只跑核心池",
        "pit_time": "snapshot_at / fetched_at",
        "dedupe": "security_id + fiscal_period_end + period_type + data_hash",
        "runtime": "核心池约 15-30 分钟",
    },
    {
        "layer": "pit",
        "table": "pit.analyst_snapshot",
        "model": AnalystSnapshot,
        "latest_field": "fetched_at",
        "purpose": "目标价、评级分布、分析师共识情绪",
        "cadence": "可跟 estimates 同跑，也可降频到每周 2-3 次",
        "pit_time": "snapshot_at / fetched_at",
        "dedupe": "security_id + data_hash",
        "runtime": "包含在 estimates 任务内",
    },
    {
        "layer": "pit",
        "table": "pit.metric_observation",
        "model": MetricObservation,
        "latest_field": "fetched_at",
        "purpose": "市值、Beta、均量、公司 profile、通用衍生指标",
        "cadence": "随日线、estimates、profile 补全任务写入",
        "pit_time": "event_at / period_end / fetched_at",
        "dedupe": "security_id + metric_code + period_end + data_hash",
        "runtime": "随采集任务",
    },
    {
        "layer": "pit",
        "table": "pit.earnings_calendar_snapshot",
        "model": EarningsCalendarSnapshot,
        "latest_field": "fetched_at",
        "purpose": "财报日历、预计值、实际值、超预期",
        "cadence": "每日事件窗口；只跑财报日前后公司",
        "pit_time": "fiscal_period_end + fetched_at",
        "dedupe": "security_id + fiscal_period_end + data_hash",
        "runtime": "事件驱动，通常秒级到分钟级",
    },
    {
        "layer": "pit",
        "table": "pit.financial_fact_snapshot",
        "model": FinancialFactSnapshot,
        "latest_field": "fetched_at",
        "purpose": "利润表、资产负债表、现金流、指标、增长率",
        "cadence": "按财报事件抓，不做每日全量",
        "pit_time": "accepted_at / filing_date / fetched_at",
        "dedupe": "security_id + dataset_code + period + data_hash",
        "runtime": "财报日公司分钟级；全量基线很慢",
    },
    {
        "layer": "pit",
        "table": "pit.news_item_snapshot",
        "model": NewsItemSnapshot,
        "latest_field": "fetched_at",
        "purpose": "公司新闻、公告、当天可见的信息流",
        "cadence": "只取当天或事件窗口，避免重复旧新闻",
        "pit_time": "published_at / fetched_at",
        "dedupe": "security_id + url/title/date + data_hash",
        "runtime": "按事件池跑，分钟级",
    },
    {
        "layer": "pit",
        "table": "pit.sec_filing_snapshot",
        "model": SecFilingSnapshot,
        "latest_field": "fetched_at",
        "purpose": "8-K、10-Q、10-K 文件链接与披露时间",
        "cadence": "财报日前后或每日少量扫描",
        "pit_time": "accepted_at / fetched_at",
        "dedupe": "security_id + form_type + accepted_at + data_hash",
        "runtime": "按事件池跑，分钟级",
    },
    {
        "layer": "pit",
        "table": "pit.earning_transcript_snapshot",
        "model": EarningTranscriptSnapshot,
        "latest_field": "fetched_at",
        "purpose": "财报电话会原文和链接",
        "cadence": "财报后定时补，不每日全量",
        "pit_time": "fiscal_year + fiscal_period + fetched_at",
        "dedupe": "security_id + fiscal_year + fiscal_period + data_hash",
        "runtime": "按事件池跑，分钟级",
    },
    {
        "layer": "pit",
        "table": "pit.macro_event_snapshot",
        "model": MacroEventSnapshot,
        "latest_field": "observed_at_utc",
        "purpose": "CPI、PPI、非农、FOMC 等宏观日历和公布值",
        "cadence": "按宏观发布时间附近轮询",
        "pit_time": "release_at_utc + observed_at_utc",
        "dedupe": "event_key + payload_hash",
        "runtime": "单次请求，秒级",
    },
    {
        "layer": "pit",
        "table": "pit.source_document_snapshot",
        "model": SourceDocumentSnapshot,
        "latest_field": "fetched_at",
        "purpose": "新闻稿、SEC、电话会等文档统一索引",
        "cadence": "随 news / sec / transcript 写入",
        "pit_time": "published_at / fetched_at",
        "dedupe": "document_type + document_key + data_hash",
        "runtime": "随文档任务",
    },
    {
        "layer": "raw",
        "table": "raw.payload",
        "model": RawPayload,
        "latest_field": "fetched_at",
        "purpose": "原始响应元数据，JSON gzip 文件留档",
        "cadence": "所有采集任务都会写",
        "pit_time": "fetched_at",
        "dedupe": "source_id + dataset_code + request_key + fetched_at + content_hash",
        "runtime": "随采集任务",
    },
    {
        "layer": "raw",
        "table": "raw.dataset_coverage",
        "model": DatasetCoverage,
        "latest_field": "last_checked_at",
        "purpose": "记录 ok/no_data/transient_failed，减少无意义重试",
        "cadence": "每次采集后更新",
        "pit_time": "last_checked_at / next_check_after",
        "dedupe": "source_code + dataset_code + symbol",
        "runtime": "随采集任务",
    },
    {
        "layer": "raw",
        "table": "raw.ingest_run",
        "model": IngestRun,
        "latest_field": "created_at",
        "purpose": "采集子任务审计、失败定位、耗时统计",
        "cadence": "每个 chunk 一条",
        "pit_time": "started_at / finished_at",
        "dedupe": "运行记录保留，不按业务去重",
        "runtime": "随采集任务",
    },
]

RUNTIME_OPTIMIZATION_ROWS = [
    {
        "方向": "分层股票池",
        "做法": "生产任务只跑核心 1500 支；候选池只用于半月重筛",
        "影响": "减少脏数据和空请求，estimates 约 15-30 分钟",
    },
    {
        "方向": "拆 endpoint 频率",
        "做法": "EPS/营收预期每天跑；目标价和评级可降频或只跑核心池",
        "影响": "减少每只股票的请求数，最直接",
    },
    {
        "方向": "快照模式去重",
        "做法": "每次都抓核心池，但只有 data_hash 变化才插入新版本",
        "影响": "保持 PIT 完整，同时避免数据库无限膨胀",
    },
    {
        "方向": "coverage 冷却",
        "做法": "无数据/不支持/长期失败 ticker 进入冷却期，不天天重试",
        "影响": "减少尾部小票、ADR、冷门 ticker 的空跑耗时",
    },
    {
        "方向": "HTTP 连接复用",
        "做法": "把 urllib 单次连接改成 httpx/requests session 或 async client",
        "影响": "减少连接开销，对多 endpoint 批量任务有帮助",
    },
    {
        "方向": "并发与限流",
        "做法": "在 600/min 限额内调高 worker，并保留 3-5 秒轻重试",
        "影响": "提升吞吐，但要防止网关随机断连放大",
    },
]


def render() -> None:
    st.set_page_config(page_title="PIT Radar", layout="wide")
    st.title("美股 Point-in-Time 数据库")
    page = st.sidebar.radio(
        "页面",
        [
            "系统概览",
            "基本面拐点雷达",
            "股票详情",
            "宏观日历",
            "任务看板",
            "数据架构",
            "PIT 时间回放",
            "数据字典",
        ],
    )

    if page == "系统概览":
        _overview_page()
    elif page == "基本面拐点雷达":
        _inflection_radar_page()
    elif page == "股票详情":
        _stock_detail_page()
    elif page == "宏观日历":
        _macro_calendar_page()
    elif page == "任务看板":
        _task_status_page()
    elif page == "数据架构":
        _data_architecture_page()
    elif page == "PIT 时间回放":
        _pit_replay_page()
    elif page == "数据字典":
        dictionary_df = pd.DataFrame(dictionary_rows()).rename(
            columns={
                "table": "表",
                "field": "英文字段",
                "name_zh": "中文名称",
                "description_zh": "中文解释",
                "data_type": "数据类型",
                "unit": "单位",
                "example": "示例",
            }
        )
        st.dataframe(dictionary_df, width="stretch", hide_index=True)


def _inflection_radar_page() -> None:
    st.subheader("基本面拐点雷达")
    st.caption(
        "寻找盈利预期上修、基本面加速、价格确认但仍有估值空间的中期研究候选。"
        "当前只用于观察，不生成交易指令。"
    )
    watchlist_files = sorted(INFLECTION_RADAR_DIR.glob("inflection_watchlist_*.csv"))
    if not watchlist_files:
        st.info(
            "尚未生成候选榜。运行："
            "`python scripts/build_inflection_watchlist.py`"
        )
        return

    watchlist_path = watchlist_files[-1]
    signal_date = watchlist_path.stem.removeprefix("inflection_watchlist_")
    report_path = INFLECTION_RADAR_DIR / f"inflection_report_{signal_date}.json"
    watchlist = pd.read_csv(watchlist_path)
    report = {}
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            report = {}
    audit = report.get("audit", {}) if isinstance(report, dict) else {}

    metric_cols = st.columns(4)
    metric_cols[0].metric("信号日期", signal_date)
    metric_cols[1].metric("候选数量", len(watchlist))
    metric_cols[2].metric("可筛选股票", audit.get("eligible_symbols", "—"))
    coverage = audit.get("median_data_coverage")
    metric_cols[3].metric(
        "中位数据覆盖",
        f"{float(coverage):.0%}" if coverage is not None else "—",
    )

    history_days = audit.get("price_history_days_median")
    if history_days is not None and float(history_days) < 60:
        st.warning(
            f"价格历史中位数目前只有 {float(history_days):.0f} 个交易日；"
            "20/60/120日价格确认和前瞻回测仍需完成历史行情回填。"
        )

    display_columns = {
        "watch_rank": "排名",
        "symbol": "股票",
        "company_name": "公司",
        "sector": "行业",
        "inflection_score": "拐点分",
        "revision_score": "预期上修",
        "fundamental_score": "基本面",
        "confirmation_score": "价格确认",
        "valuation_score": "估值空间",
        "catalyst_score": "催化剂",
        "risk_penalty": "风险扣分",
        "inflection_data_coverage": "数据覆盖",
        "q_eps_revision_20d": "EPS预期20日变化",
        "q_revenue_revision_20d": "营收预期20日变化",
        "sector_relative_return_20d": "20日行业超额",
        "target_upside": "目标价空间",
        "inflection_reason": "入选原因",
    }
    visible = [column for column in display_columns if column in watchlist]
    table = watchlist[visible].rename(columns=display_columns)
    for percent_column in (
        "数据覆盖",
        "EPS预期20日变化",
        "营收预期20日变化",
        "20日行业超额",
        "目标价空间",
    ):
        if percent_column in table:
            table[percent_column] = pd.to_numeric(table[percent_column], errors="coerce") * 100.0
    st.dataframe(
        table,
        width="stretch",
        hide_index=True,
        column_config={
            "拐点分": st.column_config.NumberColumn(format="%.1f"),
            "预期上修": st.column_config.NumberColumn(format="%.1f"),
            "基本面": st.column_config.NumberColumn(format="%.1f"),
            "价格确认": st.column_config.NumberColumn(format="%.1f"),
            "估值空间": st.column_config.NumberColumn(format="%.1f"),
            "催化剂": st.column_config.NumberColumn(format="%.1f"),
            "风险扣分": st.column_config.NumberColumn(format="%.1f"),
            "数据覆盖": st.column_config.NumberColumn(format="%.0f%%"),
            "EPS预期20日变化": st.column_config.NumberColumn(format="%.1f%%"),
            "营收预期20日变化": st.column_config.NumberColumn(format="%.1f%%"),
            "20日行业超额": st.column_config.NumberColumn(format="%.1f%%"),
            "目标价空间": st.column_config.NumberColumn(format="%.1f%%"),
            "入选原因": st.column_config.TextColumn(width="large"),
        },
    )

    evaluation = report.get("forward_evaluation", {}).get("horizons", {})
    if evaluation:
        st.subheader("前瞻验证")
        evaluation_rows = []
        for horizon, values in evaluation.items():
            evaluation_rows.append(
                {
                    "持有交易日": horizon,
                    "成熟信号日": values.get("matured_signal_dates", 0),
                    "候选平均收益": values.get("average_watchlist_return"),
                    "行业超额收益": values.get("average_watchlist_excess_return"),
                    "超额为正比例": values.get("positive_excess_hit_rate"),
                    "状态": values.get("status"),
                }
            )
        evaluation_frame = pd.DataFrame(evaluation_rows)
        for percent_column in ("候选平均收益", "行业超额收益", "超额为正比例"):
            evaluation_frame[percent_column] = pd.to_numeric(
                evaluation_frame[percent_column], errors="coerce"
            ) * 100.0
        st.dataframe(
            evaluation_frame,
            width="stretch",
            hide_index=True,
            column_config={
                "候选平均收益": st.column_config.NumberColumn(format="%.2f%%"),
                "行业超额收益": st.column_config.NumberColumn(format="%.2f%%"),
                "超额为正比例": st.column_config.NumberColumn(format="%.1f%%"),
            },
        )


def _session():
    return create_session_factory()()


def _zh_enum(value: str | None) -> str:
    return ENUM_LABELS_ZH.get(value or "", value or "暂无数据")


def _data_architecture_page() -> None:
    st.subheader("数据架构")
    st.graphviz_chart(
        """
digraph {
  rankdir=LR;
  graph [pad="0.3", nodesep="0.6", ranksep="0.8"];
  node [shape=box, style="rounded,filled", fillcolor="#F7F8FA", color="#D8DDE6", fontname="Helvetica", fontsize=11];
  edge [color="#8A94A6", arrowsize=0.8];

  fmp [label="FMP / 外部数据源", fillcolor="#EEF5FF"];
  collectors [label="采集脚本\\n限流/重试/断点", fillcolor="#F4F8EA"];
  raw [label="raw.payload\\n原始 JSON 留档", fillcolor="#FFF7E8"];
  parser [label="解析器\\n字段映射/标准化 hash", fillcolor="#F4F8EA"];
  core [label="core.*\\n证券主数据/股票池", fillcolor="#EEF5FF"];
  pit [label="pit.*\\n可回放快照表", fillcolor="#EFFFF4"];
  asof [label="As-Of 查询\\ncutoff 前最新版本", fillcolor="#F7F0FF"];
  st [label="Streamlit 看板\\n详情/任务/回放", fillcolor="#F7F8FA"];

  fmp -> collectors -> raw -> parser -> pit -> asof -> st;
  core -> parser;
  core -> asof;
}
        """
    )

    with _session() as db:
        rows = []
        for item in DATASET_ARCHITECTURE:
            count, latest = _model_count_and_latest(db, item["model"], item["latest_field"])
            rows.append(
                {
                    "层": item["layer"],
                    "表": item["table"],
                    "当前行数": _format_number_compact(count),
                    "最近时间": _format_time(latest),
                    "用途": item["purpose"],
                    "更新节奏": item["cadence"],
                    "PIT时间字段": item["pit_time"],
                    "去重/版本键": item["dedupe"],
                    "运行耗时": item["runtime"],
                }
            )

        total_pit_rows = sum(
            _model_count_and_latest(db, item["model"], item["latest_field"])[0]
            for item in DATASET_ARCHITECTURE
            if item["layer"] == "pit"
        )
        raw_rows = _model_count_and_latest(db, RawPayload, "fetched_at")[0]
        latest_pit_time = max(
            (
                _model_count_and_latest(db, item["model"], item["latest_field"])[1]
                for item in DATASET_ARCHITECTURE
                if item["layer"] == "pit"
            ),
            default=None,
        )
        securities = _model_count_and_latest(db, Security, "updated_at")[0]

        metric_cols = st.columns(4)
        metric_cols[0].metric("证券主体", _format_number_compact(securities))
        metric_cols[1].metric("PIT快照行", _format_number_compact(total_pit_rows))
        metric_cols[2].metric("原始载荷", _format_number_compact(raw_rows))
        metric_cols[3].metric("最新PIT时间", _format_time(latest_pit_time))

        st.dataframe(
            pd.DataFrame(rows),
            width="stretch",
            hide_index=True,
            column_config={
                "用途": st.column_config.TextColumn("用途", width="large"),
                "更新节奏": st.column_config.TextColumn("更新节奏", width="medium"),
                "去重/版本键": st.column_config.TextColumn("去重/版本键", width="large"),
                "运行耗时": st.column_config.TextColumn("运行耗时", width="medium"),
            },
        )

        coverage_df = _coverage_status_frame(db)
        if not coverage_df.empty:
            st.subheader("覆盖状态")
            st.dataframe(coverage_df, width="stretch", hide_index=True)

    st.subheader("PIT 回测读取方式")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "步骤": "1. 确定 cutoff",
                    "说明": "用回测当时能看到的时间，例如 2026-07-15 16:30 America/New_York。",
                },
                {
                    "步骤": "2. 取 cutoff 前最新版本",
                    "说明": "每张快照表按 security_id、业务周期字段分组，选择 fetched_at <= cutoff 的最新 data_hash 版本。",
                },
                {
                    "步骤": "3. 事件表按发布时间过滤",
                    "说明": "财报、新闻、SEC、宏观事件还要满足 published/accepted/release 时间不晚于 cutoff。",
                },
                {
                    "步骤": "4. 不覆盖历史",
                    "说明": "实际值、预期值、公布时间、评级、原始字段变化都追加新版本，不覆盖旧版本。",
                },
            ]
        ),
        width="stretch",
        hide_index=True,
        column_config={"说明": st.column_config.TextColumn("说明", width="large")},
    )

    st.subheader("缩短运行时间")
    st.dataframe(
        pd.DataFrame(RUNTIME_OPTIMIZATION_ROWS),
        width="stretch",
        hide_index=True,
        column_config={
            "做法": st.column_config.TextColumn("做法", width="large"),
            "影响": st.column_config.TextColumn("影响", width="large"),
        },
    )


def _model_count_and_latest(db, model: object, latest_field: str) -> tuple[int, datetime | None]:
    try:
        count = db.scalar(select(func.count()).select_from(model)) or 0
    except Exception:
        count = 0
    latest = None
    try:
        column = getattr(model, latest_field)
        latest = db.scalar(select(func.max(column)))
    except Exception:
        latest = None
    if isinstance(latest, datetime):
        latest = ensure_utc(latest)
    return int(count), latest


def _coverage_status_frame(db) -> pd.DataFrame:
    rows = db.execute(
        select(
            DatasetCoverage.dataset_code,
            DatasetCoverage.status,
            func.count().label("count"),
            func.max(DatasetCoverage.last_checked_at).label("latest_checked_at"),
        )
        .group_by(DatasetCoverage.dataset_code, DatasetCoverage.status)
        .order_by(DatasetCoverage.dataset_code, DatasetCoverage.status)
    ).all()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(
        {
            "数据集": [row.dataset_code for row in rows],
            "状态": [row.status for row in rows],
            "数量": [_format_number_compact(row.count) for row in rows],
            "最近检查": [_format_time(ensure_utc(row.latest_checked_at) if row.latest_checked_at else None) for row in rows],
        }
    )


def _overview_page() -> None:
    with _session() as db:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("证券数量", db.scalar(select(func.count(Security.security_id))) or 0)
        today = utc_now().date()
        runs_today = db.scalars(select(IngestRun).where(func.date(IngestRun.created_at) == str(today))).all()
        col2.metric("今日采集任务", len(runs_today))
        col3.metric("成功任务", sum(1 for run in runs_today if run.status == "success"))
        col4.metric("失败任务", sum(1 for run in runs_today if run.status == "failed"))

        st.subheader("最近 30 天采集记录")
        since = datetime.now(tz=UTC) - timedelta(days=30)
        runs = db.scalars(select(IngestRun).where(IngestRun.created_at >= since).order_by(IngestRun.created_at)).all()
        if not runs:
            st.info("暂无数据")
            return
        df = pd.DataFrame(
            {
                "日期": [run.created_at.date() for run in runs],
                "状态": [_zh_enum(run.status) for run in runs],
                "任务": [run.job_name for run in runs],
            }
        )
        trend = df.groupby(["日期", "状态"]).size().reset_index(name="数量")
        st.plotly_chart(px.bar(trend, x="日期", y="数量", color="状态"), width="stretch")
        st.dataframe(df, width="stretch")


def _stock_detail_page() -> None:
    with _session() as db:
        security = _select_security(db, "stock_detail_security")
        if security is None:
            st.warning("暂无数据")
            return
        security_id = security.security_id
        _render_company_summary(db, security)

        estimates = db.scalars(
            select(EstimateSnapshot)
            .where(EstimateSnapshot.security_id == security_id)
            .order_by(EstimateSnapshot.fiscal_period_end, EstimateSnapshot.fetched_at)
        ).all()
        if estimates:
            st.subheader("盈利与营收预期")
            _render_estimate_tables(estimates)
        else:
            st.info("暂无预期数据")

        _render_financial_facts(db, security_id)
        _render_news(db, security_id)
        _render_source_documents(db, security_id)

        bars = db.scalars(
            select(DailyMarketBar)
            .where(DailyMarketBar.security_id == security_id)
            .order_by(DailyMarketBar.trade_date, DailyMarketBar.fetched_at, DailyMarketBar.revision_no)
        ).all()
        if bars:
            latest_bars = _latest_bars_by_trade_date(bars)
            df = pd.DataFrame(
                {
                    "交易日期": [row.trade_date for row in latest_bars],
                    "收盘价": [_format_decimal(row.close) for row in latest_bars],
                    "成交量": [_format_number_compact(row.volume) for row in latest_bars],
                    "版本": [row.revision_no for row in latest_bars],
                    "获取时间": [_format_time(row.fetched_at) for row in latest_bars],
                }
            )
            chart_df = pd.DataFrame({"交易日期": [row.trade_date for row in latest_bars], "收盘价": [_to_float(row.close) for row in latest_bars]})
            st.subheader("日线行情")
            st.plotly_chart(px.line(chart_df, x="交易日期", y="收盘价", markers=True), width="stretch")
            st.dataframe(df, width="stretch", hide_index=True)
            if len(bars) > len(latest_bars):
                with st.expander(f"版本历史 ({len(bars) - len(latest_bars)} 条旧版本)"):
                    version_df = pd.DataFrame(
                        {
                            "交易日期": [row.trade_date for row in bars],
                            "收盘价": [_format_decimal(row.close) for row in bars],
                            "成交量": [_format_number_compact(row.volume) for row in bars],
                            "版本": [row.revision_no for row in bars],
                            "获取时间": [_format_time(row.fetched_at) for row in bars],
                        }
                    )
                    st.dataframe(version_df, width="stretch", hide_index=True)


def _macro_calendar_page() -> None:
    with _session() as db:
        st.subheader("宏观事件监控")
        countries = db.scalars(select(MacroEventSnapshot.country).distinct().order_by(MacroEventSnapshot.country)).all()
        country_options = ["全部"] + [country for country in countries if country]
        filter_cols = st.columns([1, 1, 2, 1])
        selected_country = filter_cols[0].selectbox("国家/地区", country_options, index=0)
        selected_window = filter_cols[1].selectbox("时间窗口", MACRO_WINDOW_OPTIONS, index=0)
        keyword = filter_cols[2].text_input("事件搜索", placeholder="CPI / FOMC / Payrolls")
        limit = filter_cols[3].slider("显示条数", min_value=50, max_value=500, value=200, step=50)

        stmt = select(MacroEventSnapshot).order_by(desc(MacroEventSnapshot.release_at_utc), desc(MacroEventSnapshot.observed_at_utc)).limit(2000)
        if selected_country != "全部":
            stmt = stmt.where(MacroEventSnapshot.country == selected_country)
        all_rows = db.scalars(stmt).all()
        if not all_rows:
            st.info("暂无宏观日历数据")
            return

        impact_options = sorted(
            {_macro_impact_key(row.impact) for row in all_rows if row.impact},
            key=lambda value: MACRO_IMPACT_ORDER.get(value, 99),
        )
        selected_impacts = st.multiselect(
            "影响等级",
            impact_options,
            default=impact_options,
            format_func=_macro_impact_label,
        )

        now = utc_now()
        rows = [
            row
            for row in all_rows
            if _macro_window_contains(row, selected_window, now)
            and _macro_keyword_matches(row, keyword)
            and (not selected_impacts or _macro_impact_key(row.impact) in selected_impacts)
        ]
        if not rows:
            st.info("当前筛选条件下暂无宏观日历数据")
            return

        version_counts = _macro_version_counts(all_rows)
        visible_rows = rows[:limit]
        metric_cols = st.columns(4)
        metric_cols[0].metric("事件数", len(rows))
        metric_cols[1].metric("高影响", sum(1 for row in rows if _macro_impact_key(row.impact) == "High"))
        metric_cols[2].metric("已有实际值", sum(1 for row in rows if _has_macro_actual(row)))
        latest_observed = max((row.observed_at_utc for row in rows if row.observed_at_utc), default=None)
        metric_cols[3].metric("最新观察", _format_time(latest_observed))

        monitor_tab, version_tab, field_tab = st.tabs(["事件监控", "版本追踪", "字段说明"])
        with monitor_tab:
            chart_df = pd.DataFrame(
                [
                    {
                        "日期": to_new_york(row.release_at_utc).date() if row.release_at_utc else None,
                        "影响": _macro_impact_label(row.impact),
                    }
                    for row in rows
                    if row.release_at_utc
                ]
            )
            if not chart_df.empty:
                trend = chart_df.groupby(["日期", "影响"]).size().reset_index(name="事件数")
                st.plotly_chart(px.bar(trend, x="日期", y="事件数", color="影响"), width="stretch")

            st.markdown("### 事件明细")
            df = pd.DataFrame([_macro_table_row(row, version_counts.get(row.event_key, 1), now) for row in visible_rows])
            st.dataframe(
                df,
                width="stretch",
                hide_index=True,
                column_config={
                    "事件": st.column_config.TextColumn("事件", width="large"),
                    "事件键": st.column_config.TextColumn("事件键", width="medium"),
                },
            )

        with version_tab:
            versioned_rows = [row for row in rows if version_counts.get(row.event_key, 1) > 1]
            if not versioned_rows:
                st.info("当前筛选范围内暂无多版本宏观事件")
            else:
                version_df = pd.DataFrame(
                    [
                        {
                            "事件": _macro_event_name(row),
                            "公布时间": _format_time(row.release_at_utc),
                            "影响": _macro_impact_label(row.impact),
                            "实际": _macro_value(row.actual_raw, row.actual_value, row.unit),
                            "预期": _macro_value(row.estimate_raw, row.estimate_value, row.unit),
                            "前值": _macro_value(row.previous_raw, row.previous_value, row.unit),
                            "观察时间": _format_time(row.observed_at_utc),
                            "版本数": version_counts.get(row.event_key, 1),
                            "载荷哈希": row.payload_hash[:12],
                            "事件键": row.event_key,
                        }
                        for row in versioned_rows[:limit]
                    ]
                )
                st.dataframe(version_df, width="stretch", hide_index=True)

        with field_tab:
            macro_dictionary = pd.DataFrame(
                [
                    {
                        "字段": row["field"],
                        "中文名称": row["name_zh"],
                        "中文解释": row["description_zh"],
                        "数据类型": row["data_type"],
                    }
                    for row in dictionary_rows()
                    if row["table"] == "pit.macro_event_snapshot"
                ]
            )
            st.dataframe(macro_dictionary, width="stretch", hide_index=True)


def _task_status_page() -> None:
    st.subheader("自动任务监控看板")
    st.caption("这里读取本机 launchd、任务运行历史和 logs/status 文件，只展示运行状态，不展示 API Key 或飞书 webhook。")

    schedule_config = _read_task_schedule_config()
    launchd_status = _launchd_statuses()
    rows = [_scheduled_task_row(task, launchd_status.get(task["label"], {}), schedule_config) for task in SCHEDULED_TASKS]
    history = _read_task_history()
    _render_task_dashboard(rows, history)

    history_tab, task_tab, settings_tab, ingest_tab, reminder_tab, logs_tab = st.tabs(["运行历史", "任务详情", "任务设置", "采集子任务", "宏观提醒", "最近日志"])
    with history_tab:
        _render_task_history_panel(history)
    with task_tab:
        _render_task_details(rows)
    with settings_tab:
        _render_task_settings_panel(schedule_config)
    with ingest_tab:
        _render_ingest_run_monitor()
    with reminder_tab:
        _render_macro_reminder_panel()
    with logs_tab:
        _render_recent_logs_panel()


def _render_task_dashboard(rows: list[dict[str, str]], history: list[dict[str, object]]) -> None:
    now = utc_now()
    recent_history = [
        record
        for record in history
        if (recorded_at := _record_datetime(record, "recorded_at")) is not None and recorded_at >= now - timedelta(hours=24)
    ]
    running = sum(1 for row in rows if row["状态"] == "运行中")
    loaded = sum(1 for row in rows if row["状态"] != "未加载")
    success_24h = sum(1 for record in recent_history if record.get("status") == "success")
    failed_24h = sum(1 for record in recent_history if record.get("status") == "failed")

    metric_cols = st.columns(5)
    metric_cols[0].metric("自动任务", len(rows))
    metric_cols[1].metric("已加载", loaded)
    metric_cols[2].metric("运行中", running)
    metric_cols[3].metric("24h成功", success_24h)
    metric_cols[4].metric("24h失败", failed_24h)

    latest_by_label = _latest_history_by_label(history)
    dashboard_rows = []
    for row in rows:
        latest = latest_by_label.get(row["Label"], {})
        latest_status = _history_status_label(latest.get("status")) if latest else _exit_status_label(row["脚本退出码"])
        if row["状态"] == "运行中":
            latest_status = "运行中"
        dashboard_rows.append(
            {
                "任务": row["任务"],
                "启用": row["启用"],
                "当前状态": row["状态"],
                "最近结果": latest_status,
                "最近开始": _format_status_time(latest.get("started_at")) if latest else row["最近开始"],
                "最近完成": _format_status_time(latest.get("finished_at")) if latest else row["最近完成"],
                "最近退出码": latest.get("exit_code", row["脚本退出码"]) if latest else row["脚本退出码"],
                "launchd退出码": row["最近退出码"],
                "耗时": _duration_label(latest.get("duration_seconds")) if latest else "暂无数据",
                "计划": row["计划"],
                "最近日志": latest.get("log_file") or row["最近日志"],
            }
        )
    st.dataframe(
        pd.DataFrame(dashboard_rows),
        width="stretch",
        hide_index=True,
        column_config={"最近日志": st.column_config.TextColumn("最近日志", width="large")},
    )

    failed_records = [record for record in history if record.get("status") == "failed"]
    if failed_records:
        st.markdown("### 最近失败")
        failure_df = pd.DataFrame([_task_history_row(record) for record in failed_records[:10]])
        st.dataframe(
            failure_df,
            width="stretch",
            hide_index=True,
            column_config={"摘要": st.column_config.TextColumn("摘要", width="large")},
        )
    elif history:
        st.success("任务历史里暂时没有失败记录。")
    else:
        st.info("任务历史文件还没有记录；从下一次自动任务结束开始，会写入 logs/task_runs.jsonl。")


def _render_task_history_panel(history: list[dict[str, object]]) -> None:
    if not history:
        st.info("暂无任务运行历史。")
        return
    limit = st.slider("显示历史条数", min_value=20, max_value=500, value=100, step=20)
    df = pd.DataFrame([_task_history_row(record) for record in history[:limit]])
    st.dataframe(
        df,
        width="stretch",
        hide_index=True,
        column_config={
            "摘要": st.column_config.TextColumn("摘要", width="large"),
            "日志": st.column_config.TextColumn("日志", width="large"),
        },
    )

    chart_df = pd.DataFrame(
        [
            {
                "日期": _record_datetime(record, "finished_at").date() if _record_datetime(record, "finished_at") else None,
                "任务": record.get("task") or record.get("label"),
                "状态": _history_status_label(record.get("status")),
            }
            for record in history
        ]
    ).dropna()
    if not chart_df.empty:
        trend = chart_df.groupby(["日期", "状态"]).size().reset_index(name="次数")
        by_task = chart_df.groupby(["任务", "状态"]).size().reset_index(name="次数")
        chart_cols = st.columns(2)
        chart_cols[0].plotly_chart(px.bar(trend, x="日期", y="次数", color="状态"), width="stretch")
        chart_cols[1].plotly_chart(px.bar(by_task, x="任务", y="次数", color="状态"), width="stretch")


def _render_ingest_run_monitor() -> None:
    since = utc_now() - timedelta(days=7)
    with _session() as db:
        runs = db.scalars(select(IngestRun).where(IngestRun.created_at >= since).order_by(desc(IngestRun.created_at)).limit(1000)).all()
    if not runs:
        st.info("最近 7 天暂无采集子任务记录。")
        return
    run_rows = [
        {
            "创建时间": _format_time(run.created_at),
            "任务": run.job_name,
            "状态": _zh_enum(run.status),
            "请求": run.requested_count,
            "成功": run.success_count,
            "失败": run.failed_count,
            "跳过": run.skipped_count,
            "开始": _format_time(run.started_at),
            "结束": _format_time(run.finished_at),
        }
        for run in runs
    ]
    df = pd.DataFrame(run_rows)
    metric_cols = st.columns(4)
    metric_cols[0].metric("子任务数", len(runs))
    metric_cols[1].metric("成功", sum(1 for run in runs if run.status == "success"))
    metric_cols[2].metric("部分成功", sum(1 for run in runs if run.status == "partial_success"))
    metric_cols[3].metric("失败", sum(1 for run in runs if run.status == "failed"))
    trend = df.groupby(["任务", "状态"]).size().reset_index(name="次数")
    st.plotly_chart(px.bar(trend, x="任务", y="次数", color="状态"), width="stretch")
    st.dataframe(df, width="stretch", hide_index=True)


def _scheduled_task_row(task: dict[str, object], launchd: dict[str, str], schedule_config: dict[str, object]) -> dict[str, str]:
    status_file = _latest_file(task["status_patterns"])
    status = _parse_status_file(status_file) if status_file else {}
    log_file = _status_log_path(status.get("log")) or _latest_file(task["log_patterns"])
    launch_pid = launchd.get("pid", "-")
    launch_exit = launchd.get("status", "未加载")
    task_schedule = _task_schedule_config(schedule_config, str(task["label"]), task)
    enabled = bool(task_schedule.get("enabled", True))
    return {
        "任务": str(task["name"]),
        "启用": "开启" if enabled else "关闭",
        "状态": "运行中" if launch_pid != "-" else ("已加载" if launch_exit != "未加载" else "未加载"),
        "最近退出码": launch_exit,
        "脚本退出码": status.get("exit_code", "暂无数据"),
        "最近开始": _format_status_time(status.get("started_at")),
        "最近完成": _format_status_time(status.get("finished_at")),
        "计划": _schedule_label(task_schedule),
        "最近日志": _relative_path(log_file) if log_file else "暂无运行记录",
        "Label": str(task["label"]),
    }


def _render_task_details(rows: list[dict[str, str]]) -> None:
    for task, row in zip(SCHEDULED_TASKS, rows, strict=False):
        with st.expander(f"{row['任务']} · {row['Label']}", expanded=False):
            status_file = _latest_file(task["status_patterns"])
            status = _parse_status_file(status_file) if status_file else {}
            status_rows = [
                {"字段": "启用状态", "值": row["启用"]},
                {"字段": "launchd 状态", "值": row["状态"]},
                {"字段": "launchd 最近退出码", "值": row["最近退出码"]},
                {"字段": "计划", "值": row["计划"]},
                {"字段": "status 文件", "值": _relative_path(status_file) if status_file else "暂无运行记录"},
                {"字段": "最近开始", "值": row["最近开始"]},
                {"字段": "最近完成", "值": row["最近完成"]},
                {"字段": "脚本退出码", "值": row["脚本退出码"]},
            ]
            for key in [
                "trade_date",
                "tasks",
                "countries",
                "chunk_size",
                "max_workers",
                "retry_rounds",
                "universe_file",
                "core_size",
                "core_symbols",
                "refresh_exit_code",
                "core_exit_code",
                "backfill_exit_code",
                "command_exit_code",
            ]:
                if key in status:
                    status_rows.append({"字段": key, "值": status[key]})
            st.dataframe(pd.DataFrame(status_rows), width="stretch", hide_index=True)

            log_file = _status_log_path(status.get("log")) or _latest_file(task["log_patterns"])
            if log_file and log_file.exists():
                st.markdown("最近日志尾部")
                st.code(_tail_file(log_file, lines=30) or "日志为空", language="text")
            else:
                st.info("暂无日志")

            if task["label"] == "com.aibao.pitradar.earnings":
                _render_earnings_state_summary()


def _render_task_settings_panel(schedule_config: dict[str, object]) -> None:
    st.caption("时间按本机时区执行；当前机器时区是北京时间。关闭任务会从 launchd 卸载，重新开启会重新安装。")
    with st.form("task_schedule_settings"):
        form_rows: list[dict[str, object]] = []
        for task in SCHEDULED_TASKS:
            label = str(task["label"])
            current = _task_schedule_config(schedule_config, label, task)
            cols = st.columns([1.1, 1.8, 1.4, 2.2])
            enabled = cols[0].checkbox(str(task["name"]), value=bool(current.get("enabled", True)), key=f"schedule_enabled_{label}")
            times_text = cols[1].text_input(
                "执行时间",
                value=", ".join(str(item) for item in current.get("times", ())),
                key=f"schedule_times_{label}",
                help="支持一个或多个 HH:MM，用逗号分隔。",
            )
            if task.get("default_days"):
                days_text = cols[2].text_input(
                    "每月日期",
                    value=", ".join(str(item) for item in current.get("days", ())),
                    key=f"schedule_days_{label}",
                    help="只用于月度任务，例如 1, 15。",
                )
            else:
                cols[2].text_input("每月日期", value="每日", key=f"schedule_days_readonly_{label}", disabled=True)
                days_text = ""
            cols[3].caption(str(task["label"]))
            form_rows.append({"task": task, "enabled": enabled, "times": times_text, "days": days_text})

        submitted = st.form_submit_button("保存并应用到 launchd", type="primary")

    if not submitted:
        return

    new_config: dict[str, object] = {"timezone": "Asia/Shanghai", "tasks": {}}
    task_configs: dict[str, object] = {}
    errors: list[str] = []
    for row in form_rows:
        task = row["task"]
        label = str(task["label"])
        try:
            times = _normalize_schedule_times(str(row["times"]), default=task.get("default_times", ()))
            days = _normalize_schedule_days(str(row["days"]), default=task.get("default_days", ())) if task.get("default_days") else []
        except ValueError as exc:
            errors.append(f"{task['name']}: {exc}")
            continue
        value: dict[str, object] = {"enabled": bool(row["enabled"]), "times": times}
        if task.get("default_days"):
            value["days"] = days
        task_configs[label] = value

    if errors:
        st.error("\n".join(errors))
        return

    new_config["tasks"] = task_configs
    _write_task_schedule_config(new_config)
    result = _sync_launchd_schedule()
    if result.returncode == 0:
        st.success("任务设置已保存并同步到 launchd。")
        if result.stdout.strip():
            st.code(result.stdout.strip(), language="text")
    else:
        st.error("任务设置已保存，但同步 launchd 失败。")
        st.code((result.stderr or result.stdout or "").strip(), language="text")


def _read_task_schedule_config() -> dict[str, object]:
    try:
        data = json.loads(TASK_SCHEDULE_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = {"timezone": "Asia/Shanghai", "tasks": {}}
    if not isinstance(data, dict):
        data = {"timezone": "Asia/Shanghai", "tasks": {}}
    data.setdefault("timezone", "Asia/Shanghai")
    data.setdefault("tasks", {})
    return data


def _write_task_schedule_config(config: dict[str, object]) -> None:
    TASK_SCHEDULE_FILE.parent.mkdir(parents=True, exist_ok=True)
    TASK_SCHEDULE_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sync_launchd_schedule() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TASK_SCHEDULE_SYNC_SCRIPT), "--print-summary"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _task_schedule_config(config: dict[str, object], label: str, task: dict[str, object]) -> dict[str, object]:
    tasks = config.get("tasks") if isinstance(config.get("tasks"), dict) else {}
    raw = tasks.get(label) if isinstance(tasks, dict) and isinstance(tasks.get(label), dict) else {}
    times = raw.get("times", task.get("default_times", ())) if isinstance(raw, dict) else task.get("default_times", ())
    days = raw.get("days", task.get("default_days", ())) if isinstance(raw, dict) else task.get("default_days", ())
    return {
        "enabled": bool(raw.get("enabled", True)) if isinstance(raw, dict) else True,
        "times": _normalize_schedule_times(times, default=task.get("default_times", ())),
        "days": _normalize_schedule_days(days, default=task.get("default_days", ())) if task.get("default_days") else [],
    }


def _schedule_label(config: dict[str, object]) -> str:
    if not bool(config.get("enabled", True)):
        return "已关闭"
    times = "、".join(str(item) for item in config.get("times", ()))
    days = config.get("days") or []
    if days:
        return f"每月 {'、'.join(str(item) for item in days)} 日 {times} 北京时间"
    return f"每日 {times} 北京时间"


def _normalize_schedule_times(values: object, default: object = ()) -> list[str]:
    if isinstance(values, str):
        items = re.split(r"[,，\s]+", values)
    else:
        items = [str(item) for item in values] if values else [str(item) for item in default]
    output: list[str] = []
    for item in items:
        value = str(item).strip()
        if not value:
            continue
        if not re.fullmatch(r"\d{1,2}:\d{2}", value):
            raise ValueError(f"时间 {value} 不合法，请用 HH:MM")
        hour_text, minute_text = value.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(f"时间 {value} 不合法，请用 00:00 到 23:59")
        output.append(f"{hour:02d}:{minute:02d}")
    if not output:
        output = [str(item) for item in default]
    return list(dict.fromkeys(output))


def _normalize_schedule_days(values: object, default: object = ()) -> list[int]:
    if isinstance(values, str):
        items = re.split(r"[,，\s]+", values)
    else:
        items = values if values else default
    output: list[int] = []
    for item in items:
        if item in (None, ""):
            continue
        day = int(item)
        if not 1 <= day <= 31:
            raise ValueError(f"日期 {day} 不合法，请用 1 到 31")
        output.append(day)
    if not output:
        output = [int(item) for item in default]
    return sorted(set(output))


def _render_macro_reminder_panel() -> None:
    configured = _env_has_value("FEISHU_WEBHOOK_URL")
    secret_configured = _env_has_value("FEISHU_BOT_SECRET")
    metric_cols = st.columns(3)
    metric_cols[0].metric("飞书机器人", "已配置" if configured else "未配置")
    metric_cols[1].metric("签名密钥", "已配置" if secret_configured else "未配置")
    status_file = _latest_file(("macro_reminder.status",))
    status = _parse_status_file(status_file) if status_file else {}
    metric_cols[2].metric("最近退出码", status.get("exit_code", "暂无数据"))
    if not configured:
        st.info("未配置飞书 webhook 时，提醒脚本会正常查询候选事件，但不会发送消息。")

    st.markdown("### 未来 3 天高影响美国宏观事件")
    with _session() as db:
        upcoming = _latest_upcoming_macro_events(db, lookahead_days=3, countries=["US"], impact_levels=["High"])
    if upcoming:
        upcoming_df = pd.DataFrame(
            [
                {
                    "公布时间": _format_time(row.release_at_utc),
                    "事件": _macro_event_name(row),
                    "影响": _macro_impact_label(row.impact),
                    "预期": _macro_value(row.estimate_raw, row.estimate_value, row.unit),
                    "前值": _macro_value(row.previous_raw, row.previous_value, row.unit),
                    "实际": _macro_value(row.actual_raw, row.actual_value, row.unit),
                    "观察时间": _format_time(row.observed_at_utc),
                }
                for row in upcoming
            ]
        )
        st.dataframe(upcoming_df, width="stretch", hide_index=True)
    else:
        st.info("当前数据库里没有未来 3 天的高影响美国宏观事件。")

    state_file = LOG_DIR / "macro_event_reminders.json"
    state = _read_json_file(state_file)
    if isinstance(state, dict) and state:
        reminder_rows = []
        for key, value in state.items():
            if not isinstance(value, dict):
                continue
            reminder_rows.append(
                {
                    "发送时间": _format_status_time(value.get("sent_at")),
                    "事件": value.get("event_name") or key,
                    "公布时间": _format_status_time(value.get("release_at_utc")),
                    "影响": _macro_impact_label(str(value.get("impact") or "")),
                }
            )
        reminder_rows.sort(key=lambda item: item["发送时间"], reverse=True)
        st.markdown("### 已发送提醒")
        st.dataframe(pd.DataFrame(reminder_rows[:50]), width="stretch", hide_index=True)
    else:
        st.caption("暂无已发送提醒记录。")


def _render_earnings_state_summary() -> None:
    calendar_state = _read_json_file(LOG_DIR / "earnings_calendar_refresh.status")
    if isinstance(calendar_state, dict) and calendar_state:
        st.markdown("财报日历刷新")
        st.dataframe(
            pd.DataFrame(
                [
                    {"字段": "完成时间", "值": _format_status_time(str(calendar_state.get("finished_at") or ""))},
                    {"字段": "股票数", "值": str(calendar_state.get("symbols") or "暂无数据")},
                    {"字段": "任务批次", "值": str(len(calendar_state.get("runs") or []))},
                ]
            ),
            width="stretch",
            hide_index=True,
        )

    state = _read_json_file(LOG_DIR / "earnings_event_symbol_state.json")
    if not isinstance(state, dict) or not state:
        st.caption("暂无财报事件 symbol 状态文件。")
        return

    event_rows = [
        {
            "股票": symbol,
            "最近运行": _format_status_time(str(payload.get("last_run_at") or "")) if isinstance(payload, dict) else "暂无数据",
            "窗口": f"{payload.get('window_from')} - {payload.get('window_to')}" if isinstance(payload, dict) else "暂无数据",
        }
        for symbol, payload in state.items()
    ]
    event_rows.sort(key=lambda item: item["最近运行"], reverse=True)
    st.markdown("财报事件已处理股票")
    st.dataframe(pd.DataFrame(event_rows[:80]), width="stretch", hide_index=True)


def _render_recent_logs_panel() -> None:
    log_files: list[Path] = []
    for task in SCHEDULED_TASKS:
        for pattern in task["log_patterns"]:
            log_files.extend(LOG_DIR.glob(str(pattern)))
    log_files = sorted(set(log_files), key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True)
    if not log_files:
        st.info("暂无日志")
        return
    log_df = pd.DataFrame(
        [
            {
                "文件": _relative_path(path),
                "修改时间": _format_mtime(path),
                "大小": _format_bytes(path.stat().st_size),
            }
            for path in log_files[:30]
        ]
    )
    st.dataframe(log_df, width="stretch", hide_index=True)
    selected = st.selectbox("查看日志尾部", log_files[:30], format_func=_relative_path)
    st.code(_tail_file(selected, lines=80) or "日志为空", language="text")


def _latest_upcoming_macro_events(db, lookahead_days: int, countries: list[str], impact_levels: list[str]) -> list[MacroEventSnapshot]:
    now = utc_now()
    latest = (
        select(
            MacroEventSnapshot.id.label("event_id"),
            func.row_number()
            .over(
                partition_by=MacroEventSnapshot.event_key,
                order_by=(desc(MacroEventSnapshot.observed_at_utc), desc(MacroEventSnapshot.id)),
            )
            .label("rank"),
        )
        .subquery()
    )
    stmt = (
        select(MacroEventSnapshot)
        .join(latest, MacroEventSnapshot.id == latest.c.event_id)
        .where(
            latest.c.rank == 1,
            MacroEventSnapshot.release_at_utc >= now,
            MacroEventSnapshot.release_at_utc <= now + timedelta(days=lookahead_days),
        )
        .order_by(MacroEventSnapshot.release_at_utc, MacroEventSnapshot.event_name)
    )
    if countries:
        stmt = stmt.where(MacroEventSnapshot.country.in_(countries))
    if impact_levels:
        stmt = stmt.where(MacroEventSnapshot.impact.in_(impact_levels))
    return list(db.scalars(stmt).all())


def _pit_replay_page() -> None:
    cutoff = st.text_input("Cutoff 时间", value="2026-07-14T09:30:00-04:00")
    strict = st.toggle("严格PIT：只使用live数据", value=True)
    try:
        cutoff_time = parse_datetime(cutoff)
    except ValueError:
        st.error("时间格式不正确")
        return
    with _session() as db:
        security = _select_security(db, "pit_replay_security")
        if security is None:
            st.warning("暂无数据")
            return
        snapshot = AsOfService(db).snapshot_for_ticker(security.primary_ticker, cutoff_time, strict_live=strict)
        if snapshot["security"] is None:
            st.warning("暂无数据")
            return
        st.subheader("截至该时间系统已知数据")
        st.write(f"回放时间（纽约）：{to_new_york(cutoff_time)}")
        for key in [
            "identifier",
            "estimates",
            "analyst",
            "earnings",
            "daily_bars",
            "news",
            "financial_facts",
            "sec_filings",
            "transcripts",
            "source_documents",
            "metrics",
        ]:
            st.markdown(f"### {key}")
            value = snapshot[key]
            if not value:
                st.info("暂无数据")
            elif isinstance(value, list):
                st.dataframe([_model_row(row) for row in value], width="stretch")
            else:
                st.json(_model_row(value))


def _select_security(db, key: str) -> Security | None:
    securities = db.scalars(select(Security).order_by(Security.primary_ticker, Security.company_name)).all()
    if not securities:
        return None
    core_symbols = _load_core_symbols()
    if core_symbols:
        core_only = st.checkbox("仅显示核心池", value=True, key=f"{key}_core_only")
        if core_only:
            before_count = len(securities)
            securities = [security for security in securities if (security.primary_ticker or "").upper() in core_symbols]
            st.caption(f"核心池 {len(securities)} / 数据库证券 {before_count}")
    query = st.text_input(
        "股票 / 公司搜索",
        key=f"{key}_query",
        placeholder="输入 ticker 或公司名，例如 AAPL / Apple",
    ).strip()
    visible_securities = _filter_securities(securities, query)
    if not visible_securities:
        st.info("没有匹配的公司")
        return None
    if len(visible_securities) < len(securities):
        st.caption(f"匹配 {len(visible_securities)} / {len(securities)}")
    labels = {security.security_id: _security_option_label(security) for security in visible_securities}
    selected_id = st.selectbox(
        "公司",
        [security.security_id for security in visible_securities],
        format_func=lambda value: labels.get(value, str(value)),
        key=key,
    )
    return db.get(Security, selected_id)


def _filter_securities(securities: list[Security], query: str, limit: int = 200) -> list[Security]:
    if not query:
        return securities[:limit]
    normalized = query.strip().upper()
    exact: list[Security] = []
    prefix: list[Security] = []
    contains: list[Security] = []
    for security in securities:
        ticker = (security.primary_ticker or "").upper()
        company = (security.company_name or "").upper()
        if ticker == normalized:
            exact.append(security)
        elif ticker.startswith(normalized):
            prefix.append(security)
        elif normalized in ticker or normalized in company:
            contains.append(security)
    return (exact + prefix + contains)[:limit]


def _load_core_symbols() -> set[str]:
    if not CORE_SYMBOLS_FILE.exists():
        return set()
    symbols: set[str] = set()
    for line in CORE_SYMBOLS_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for item in stripped.replace(",", "\n").splitlines():
            symbol = item.strip().upper()
            if symbol:
                symbols.add(symbol)
    return symbols


def _security_option_label(security: Security) -> str:
    details = " / ".join(item for item in [security.exchange, security.sector] if item)
    suffix = f" ({details})" if details else ""
    return f"{security.primary_ticker} - {security.company_name or '未知公司'}{suffix}"


def _render_company_summary(db, security: Security) -> None:
    metrics = _latest_metrics(db, security.security_id)
    latest_bar = _latest_daily_bar(db, security.security_id)
    latest_price = _metric_numeric(metrics, "profile_price") or (latest_bar.close if latest_bar else None)
    latest_volume = _metric_numeric(metrics, "average_volume") or (latest_bar.volume if latest_bar else None)
    st.subheader(f"{security.primary_ticker} · {security.company_name}")
    metric_cols = st.columns(4)
    metric_cols[0].metric("最新价格", _format_money_compact(latest_price, security.currency))
    metric_cols[1].metric("市值", _format_money_compact(_metric_numeric(metrics, "market_cap"), security.currency))
    metric_cols[2].metric("Beta", _format_decimal(_metric_numeric(metrics, "beta")))
    metric_cols[3].metric("成交量", _format_number_compact(latest_volume))

    identifiers = db.scalars(
        select(SecurityIdentifier)
        .where(SecurityIdentifier.security_id == security.security_id)
        .order_by(SecurityIdentifier.identifier_type, desc(SecurityIdentifier.valid_from))
    ).all()
    id_text = ", ".join(
        f"{item.identifier_type.upper()} {item.identifier_value}"
        for item in identifiers
        if item.identifier_type in {"ticker", "cik", "cusip", "isin"}
    )
    info = pd.DataFrame(
        [
            {"字段": "交易所", "值": _missing(security.exchange)},
            {"字段": "行业", "值": _missing(security.industry)},
            {"字段": "板块", "值": _missing(security.sector)},
            {"字段": "国家/地区", "值": _missing(security.country)},
            {"字段": "货币", "值": _missing(security.currency)},
            {"字段": "最近观察", "值": _format_time(security.last_seen_at)},
            {"字段": "标识符", "值": id_text or "暂无数据"},
        ]
    )
    st.dataframe(info, width="stretch", hide_index=True)


def _latest_metrics(db, security_id: int) -> dict[str, MetricObservation]:
    rows = db.scalars(
        select(MetricObservation)
        .where(MetricObservation.security_id == security_id)
        .order_by(desc(MetricObservation.fetched_at), desc(MetricObservation.recorded_at))
    ).all()
    metrics: dict[str, MetricObservation] = {}
    for row in rows:
        metrics.setdefault(row.metric_code, row)
    return metrics


def _latest_daily_bar(db, security_id: int) -> DailyMarketBar | None:
    return db.scalar(
        select(DailyMarketBar)
        .where(DailyMarketBar.security_id == security_id)
        .order_by(desc(DailyMarketBar.trade_date), desc(DailyMarketBar.fetched_at), desc(DailyMarketBar.revision_no))
    )


def _latest_bars_by_trade_date(rows: list[DailyMarketBar]) -> list[DailyMarketBar]:
    latest: dict[date, DailyMarketBar] = {}
    for row in rows:
        current = latest.get(row.trade_date)
        if current is None or (row.fetched_at, row.revision_no) >= (current.fetched_at, current.revision_no):
            latest[row.trade_date] = row
    return [latest[key] for key in sorted(latest)]


def _metric_numeric(metrics: dict[str, MetricObservation], code: str) -> Decimal | None:
    row = metrics.get(code)
    return row.value_numeric if row else None


def _estimate_frame(estimates: list[EstimateSnapshot]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "周期": _zh_period(row.period_type),
                "报告期结束日": row.fiscal_period_end,
                "EPS均值": _format_decimal(row.eps_mean),
                "EPS区间": _format_range(row.eps_low, row.eps_high),
                "营收均值": _format_money_compact(row.revenue_mean, row.currency),
                "营收区间": _format_money_range(row.revenue_low, row.revenue_high, row.currency),
                "EPS预测分析师数": row.analyst_count_eps,
                "营收预测分析师数": row.analyst_count_revenue,
                "系统获取时间": _format_time(row.fetched_at),
            }
            for row in estimates
        ]
    )


def _render_estimate_tables(estimates: list[EstimateSnapshot]) -> None:
    df = _estimate_frame(estimates)
    table_columns = [
        "报告期结束日",
        "EPS均值",
        "EPS区间",
        "营收均值",
        "营收区间",
        "EPS预测分析师数",
        "营收预测分析师数",
        "系统获取时间",
    ]
    quarter_df = df[df["周期"] == "季度"][table_columns]
    fiscal_year_df = df[df["周期"] == "财年"][table_columns]
    quarter_tab, fiscal_year_tab = st.tabs([f"季度 ({len(quarter_df)})", f"财年 ({len(fiscal_year_df)})"])
    with quarter_tab:
        _estimate_table(quarter_df)
    with fiscal_year_tab:
        _estimate_table(fiscal_year_df)


def _estimate_table(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("暂无数据")
        return
    st.dataframe(
        df,
        width="stretch",
        hide_index=True,
        column_config={
            "EPS预测分析师数": st.column_config.NumberColumn(
                "EPS预测分析师数",
                help="FMP 一致预期中参与 EPS 预测统计的分析师数量。",
            ),
            "营收预测分析师数": st.column_config.NumberColumn(
                "营收预测分析师数",
                help="FMP 一致预期中参与营收预测统计的分析师数量。",
            ),
        },
    )


def _render_financial_facts(db, security_id: int) -> None:
    facts = db.scalars(
        select(FinancialFactSnapshot)
        .where(FinancialFactSnapshot.security_id == security_id)
        .order_by(FinancialFactSnapshot.dataset_code, desc(FinancialFactSnapshot.fiscal_period_end), desc(FinancialFactSnapshot.fetched_at))
        .limit(160)
    ).all()
    if not facts:
        return

    st.subheader("财报事实数据")
    dataset_codes = sorted({row.dataset_code for row in facts})
    selected = st.selectbox(
        "数据集",
        dataset_codes,
        format_func=lambda value: FINANCIAL_DATASET_LABELS.get(value, value),
        key=f"financial_dataset_{security_id}",
    )
    rows = [row for row in facts if row.dataset_code == selected]
    df = pd.DataFrame(
        [
            {
                "周期": _zh_period(row.period_type),
                "报告期结束日": row.fiscal_period_end or "暂无数据",
                "财年": row.fiscal_year or "暂无数据",
                "期间": row.fiscal_period or "暂无数据",
                "货币": row.reported_currency or "暂无数据",
                "核心字段": _financial_highlights(row),
                "披露/接受时间": _format_time(row.source_published_at or row.accepted_at),
                "系统获取时间": _format_time(row.fetched_at),
            }
            for row in rows
        ]
    )
    st.dataframe(df, width="stretch", hide_index=True)


def _render_news(db, security_id: int) -> None:
    news = db.scalars(
        select(NewsItemSnapshot)
        .where(NewsItemSnapshot.security_id == security_id)
        .order_by(desc(NewsItemSnapshot.published_at), desc(NewsItemSnapshot.fetched_at))
        .limit(50)
    ).all()
    if not news:
        return

    st.subheader("新闻与公告")
    df = pd.DataFrame(
        [
            {
                "发布时间": _format_time(row.published_at),
                "类型": NEWS_TYPE_LABELS.get(row.news_type, row.news_type),
                "来源": row.publisher or "暂无数据",
                "标题": row.title or "暂无数据",
                "摘要": _truncate(row.summary, 180),
                "URL": row.url,
                "系统获取时间": _format_time(row.fetched_at),
            }
            for row in news
        ]
    )
    st.dataframe(
        df,
        width="stretch",
        hide_index=True,
        column_config={"URL": st.column_config.LinkColumn("URL")},
    )


def _render_source_documents(db, security_id: int) -> None:
    filings = db.scalars(
        select(SecFilingSnapshot)
        .where(SecFilingSnapshot.security_id == security_id)
        .order_by(desc(SecFilingSnapshot.accepted_at), desc(SecFilingSnapshot.fetched_at))
        .limit(50)
    ).all()
    transcripts = db.scalars(
        select(EarningTranscriptSnapshot)
        .where(EarningTranscriptSnapshot.security_id == security_id)
        .order_by(desc(EarningTranscriptSnapshot.fiscal_year), desc(EarningTranscriptSnapshot.fiscal_period), desc(EarningTranscriptSnapshot.fetched_at))
        .limit(20)
    ).all()
    docs = db.scalars(
        select(SourceDocumentSnapshot)
        .where(SourceDocumentSnapshot.security_id == security_id)
        .order_by(desc(SourceDocumentSnapshot.source_event_at), desc(SourceDocumentSnapshot.fetched_at))
        .limit(100)
    ).all()
    if not filings and not transcripts and not docs:
        return

    st.subheader("SEC文件与电话会原文")
    filing_tab, transcript_tab, docs_tab = st.tabs([f"SEC文件 ({len(filings)})", f"电话会 ({len(transcripts)})", f"来源原文 ({len(docs)})"])
    with filing_tab:
        if not filings:
            st.info("暂无数据")
        else:
            df = pd.DataFrame(
                [
                    {
                        "接受时间": _format_time(row.accepted_at),
                        "披露日期": row.filing_date or "暂无数据",
                        "类型": row.form_type or "暂无数据",
                        "CIK": row.cik or "暂无数据",
                        "含财务数据": "是" if row.has_financials else "否" if row.has_financials is False else "暂无数据",
                        "文件": row.final_url or row.filing_url,
                        "索引": row.filing_url,
                        "系统获取时间": _format_time(row.fetched_at),
                    }
                    for row in filings
                ]
            )
            st.dataframe(
                df,
                width="stretch",
                hide_index=True,
                column_config={
                    "文件": st.column_config.LinkColumn("文件"),
                    "索引": st.column_config.LinkColumn("索引"),
                },
            )
    with transcript_tab:
        if not transcripts:
            st.info("暂无数据")
        else:
            df = pd.DataFrame(
                [
                    {
                        "年份": row.fiscal_year or "暂无数据",
                        "季度": row.fiscal_period or "暂无数据",
                        "日期": row.call_date or "暂无数据",
                        "词数": row.word_count or "暂无数据",
                        "内容预览": _truncate(row.transcript_text, 260),
                        "系统获取时间": _format_time(row.fetched_at),
                    }
                    for row in transcripts
                ]
            )
            st.dataframe(df, width="stretch", hide_index=True)
    with docs_tab:
        if not docs:
            st.info("暂无数据")
        else:
            df = pd.DataFrame(
                [
                    {
                        "事件时间": _format_time(row.source_event_at),
                        "类型": DOCUMENT_TYPE_LABELS.get(row.document_type, row.document_type),
                        "标题": row.title or "暂无数据",
                        "来源链接": row.source_url,
                        "本地原文": row.object_uri,
                        "字节数": f"{row.content_length:,}" if row.content_length else "链接",
                        "预览": _truncate(row.text_excerpt, 220),
                        "系统获取时间": _format_time(row.fetched_at),
                    }
                    for row in docs
                ]
            )
            st.dataframe(
                df,
                width="stretch",
                hide_index=True,
                column_config={
                    "来源链接": st.column_config.LinkColumn("来源链接"),
                },
            )


def _financial_highlights(row: FinancialFactSnapshot) -> str:
    data = row.value_json or {}
    currency = row.reported_currency or "USD"
    if row.dataset_code == "income_statement":
        items = [
            ("营收", _format_money_compact(_json_number(data, "revenue"), currency)),
            ("毛利", _format_money_compact(_json_number(data, "grossProfit"), currency)),
            ("净利润", _format_money_compact(_json_number(data, "netIncome"), currency)),
            ("摊薄EPS", _format_decimal(_json_number(data, "epsdiluted", "epsDiluted", "eps"))),
        ]
    elif row.dataset_code == "balance_sheet":
        items = [
            ("总资产", _format_money_compact(_json_number(data, "totalAssets"), currency)),
            ("现金", _format_money_compact(_json_number(data, "cashAndCashEquivalents"), currency)),
            ("总负债", _format_money_compact(_json_number(data, "totalLiabilities"), currency)),
            ("总债务", _format_money_compact(_json_number(data, "totalDebt"), currency)),
        ]
    elif row.dataset_code == "cash_flow":
        items = [
            ("经营现金流", _format_money_compact(_json_number(data, "netCashProvidedByOperatingActivities"), currency)),
            ("资本开支", _format_money_compact(_json_number(data, "capitalExpenditure"), currency)),
            ("自由现金流", _format_money_compact(_json_number(data, "freeCashFlow"), currency)),
        ]
    elif row.dataset_code == "ratios":
        items = [
            ("PE", _format_decimal(_json_number(data, "priceToEarningsRatio", "priceEarningsRatio", "peRatio"))),
            ("PEG", _format_decimal(_json_number(data, "priceToEarningsGrowthRatio"))),
            ("Forward PEG", _format_decimal(_json_number(data, "forwardPriceToEarningsGrowthRatio"))),
            ("PS", _format_decimal(_json_number(data, "priceToSalesRatio"))),
            ("ROE", _format_decimal(_json_number(data, "returnOnEquity"))),
            ("债务权益比", _format_decimal(_json_number(data, "debtEquityRatio"))),
        ]
    elif row.dataset_code == "key_metrics":
        items = [
            ("市值", _format_money_compact(_json_number(data, "marketCap"), currency)),
            ("企业价值", _format_money_compact(_json_number(data, "enterpriseValue"), currency)),
            ("EV/EBITDA", _format_decimal(_json_number(data, "evToEbitda"))),
            ("每股营收", _format_decimal(_json_number(data, "revenuePerShare"))),
        ]
    elif row.dataset_code == "financial_growth":
        items = [
            ("营收增长", _format_decimal(_json_number(data, "revenueGrowth"))),
            ("毛利增长", _format_decimal(_json_number(data, "grossProfitGrowth"))),
            ("EPS增长", _format_decimal(_json_number(data, "epsgrowth", "epsGrowth"))),
            ("自由现金流增长", _format_decimal(_json_number(data, "freeCashFlowGrowth"))),
        ]
    elif row.dataset_code == "financial_scores":
        items = [
            ("Altman Z", _format_decimal(_json_number(data, "altmanZScore"))),
            ("Piotroski", _format_decimal(_json_number(data, "piotroskiScore"))),
            ("营运资本", _format_money_compact(_json_number(data, "workingCapital"), currency)),
        ]
    else:
        items = []
    values = [f"{label}: {value}" for label, value in items if value != "暂无数据"]
    return "；".join(values) or "暂无核心字段映射"


def _zh_period(value: str | None) -> str:
    if value == "quarter":
        return "季度"
    if value == "fiscal_year":
        return "财年"
    return value or "暂无数据"


def _json_number(data: dict, *keys: str) -> Decimal | None:
    for key in keys:
        value = data.get(key)
        if value is None or value == "":
            continue
        try:
            return Decimal(str(value))
        except Exception:
            return None
    return None


def _truncate(value: str | None, length: int) -> str:
    if not value:
        return "暂无数据"
    text = str(value)
    return text if len(text) <= length else text[: length - 1] + "..."


def _macro_table_row(row: MacroEventSnapshot, version_count: int, now: datetime) -> dict[str, str | int]:
    return {
        "状态": "已公布" if _has_macro_actual(row) else "待公布",
        "公布时间": _format_time(row.release_at_utc),
        "距公布": _macro_release_distance(row.release_at_utc, now),
        "国家": row.country or "暂无数据",
        "货币": row.currency or "暂无数据",
        "事件": _macro_event_name(row),
        "影响": _macro_impact_label(row.impact),
        "实际": _macro_value(row.actual_raw, row.actual_value, row.unit),
        "预期": _macro_value(row.estimate_raw, row.estimate_value, row.unit),
        "预期差": _macro_surprise(row),
        "前值": _macro_value(row.previous_raw, row.previous_value, row.unit),
        "观察时间": _format_time(row.observed_at_utc),
        "版本数": version_count,
        "回填": "是" if row.is_backfill else "否",
        "事件键": row.event_key,
    }


def _macro_event_name(row: MacroEventSnapshot) -> str:
    return row.event_name_cn or row.event_name or "暂无数据"


def _macro_impact_key(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    mapping = {
        "high": "High",
        "medium": "Medium",
        "med": "Medium",
        "low": "Low",
    }
    return mapping.get(normalized, value or "未知")


def _macro_impact_label(value: str | None) -> str:
    key = _macro_impact_key(value)
    return MACRO_IMPACT_LABELS.get(key, key or "暂无数据")


def _macro_window_contains(row: MacroEventSnapshot, window: str, now: datetime) -> bool:
    if window == "全部":
        return True
    if row.release_at_utc is None:
        return False
    release_at = ensure_utc(row.release_at_utc)
    if window == "今天":
        release_day = to_new_york(release_at).date()
        return release_day == to_new_york(now).date()
    if window == "未来7天":
        return now <= release_at <= now + timedelta(days=7)
    if window == "未来30天":
        return now <= release_at <= now + timedelta(days=30)
    if window == "过去7天":
        return now - timedelta(days=7) <= release_at <= now
    return True


def _macro_keyword_matches(row: MacroEventSnapshot, keyword: str) -> bool:
    query = keyword.strip().lower()
    if not query:
        return True
    haystack = " ".join(
        value or ""
        for value in [
            row.event_name,
            row.event_name_cn,
            row.country,
            row.currency,
            row.impact,
        ]
    ).lower()
    return query in haystack


def _macro_version_counts(rows: list[MacroEventSnapshot]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.event_key] = counts.get(row.event_key, 0) + 1
    return counts


def _has_macro_actual(row: MacroEventSnapshot) -> bool:
    return row.actual_raw not in {None, ""} or row.actual_value is not None


def _macro_surprise(row: MacroEventSnapshot) -> str:
    if row.actual_value is None or row.estimate_value is None:
        return "暂无数据"
    diff = row.actual_value - row.estimate_value
    sign = "+" if diff > 0 else ""
    suffix = row.unit or ""
    return f"{sign}{_format_decimal(diff)}{suffix}"


def _macro_release_distance(value: datetime | None, now: datetime) -> str:
    if value is None:
        return "暂无数据"
    seconds = int((ensure_utc(value) - now).total_seconds())
    prefix = "还有" if seconds >= 0 else "已过"
    absolute = abs(seconds)
    days, remainder = divmod(absolute, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes = remainder // 60
    if days:
        text = f"{days}天{hours}小时"
    elif hours:
        text = f"{hours}小时{minutes}分钟"
    else:
        text = f"{minutes}分钟"
    return f"{prefix}{text}"


def _macro_value(raw: str | None, parsed: Decimal | None, unit: str | None) -> str:
    if raw not in {None, ""}:
        return str(raw)
    if parsed is None:
        return "暂无数据"
    suffix = unit or ""
    return f"{_format_decimal(parsed)}{suffix}"


def _read_task_history() -> list[dict[str, object]]:
    if not TASK_HISTORY_FILE.exists():
        return []
    records: list[dict[str, object]] = []
    seen: set[tuple[object, object, object, object]] = set()
    try:
        lines = TASK_HISTORY_FILE.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        key = (record.get("label"), record.get("started_at"), record.get("finished_at"), record.get("log_file"))
        if key in seen:
            continue
        seen.add(key)
        records.append(record)
    records.sort(key=lambda item: _record_datetime(item, "recorded_at") or datetime.min.replace(tzinfo=UTC), reverse=True)
    return records


def _latest_history_by_label(history: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    latest: dict[str, dict[str, object]] = {}
    for record in history:
        label = str(record.get("label") or "")
        if label and label not in latest:
            latest[label] = record
    return latest


def _task_history_row(record: dict[str, object]) -> dict[str, object]:
    return {
        "任务": record.get("task") or record.get("label") or "暂无数据",
        "状态": _history_status_label(record.get("status")),
        "退出码": record.get("exit_code", "暂无数据"),
        "开始": _format_status_time(record.get("started_at")),
        "结束": _format_status_time(record.get("finished_at")),
        "耗时": _duration_label(record.get("duration_seconds")),
        "日志": record.get("log_file") or "暂无数据",
        "摘要": _truncate(str(record.get("summary") or ""), 320),
    }


def _record_datetime(record: dict[str, object], key: str) -> datetime | None:
    value = record.get(key)
    if value in {None, ""}:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _history_status_label(value: object) -> str:
    if value == "success":
        return "成功"
    if value == "failed":
        return "失败"
    if value == "running":
        return "运行中"
    return str(value) if value not in {None, ""} else "暂无数据"


def _exit_status_label(value: object) -> str:
    if value in {None, "", "暂无数据"}:
        return "暂无数据"
    return "成功" if str(value) == "0" else "失败"


def _duration_label(value: object) -> str:
    if value in {None, ""}:
        return "暂无数据"
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return str(value)
    hours, remainder = divmod(max(0, seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{seconds:02d}s"
    if minutes:
        return f"{minutes}m{seconds:02d}s"
    return f"{seconds}s"


def _launchd_statuses() -> dict[str, dict[str, str]]:
    try:
        result = subprocess.run(
            ["launchctl", "list"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return {}
    statuses: dict[str, dict[str, str]] = {}
    for line in result.stdout.splitlines()[1:]:
        parts = line.split(None, 2)
        if len(parts) != 3:
            continue
        pid, status, label = parts
        if label.startswith("com.aibao.pitradar."):
            statuses[label] = {"pid": pid, "status": status}
    return statuses


def _latest_file(patterns: object) -> Path | None:
    if isinstance(patterns, str):
        pattern_values = (patterns,)
    else:
        pattern_values = tuple(str(item) for item in patterns)
    files: list[Path] = []
    for pattern in pattern_values:
        files.extend(path for path in LOG_DIR.glob(pattern) if path.is_file())
    if not files:
        return None
    return max(files, key=lambda path: path.stat().st_mtime)


def _parse_status_file(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return {}
    stripped = text.strip()
    if not stripped:
        return {}
    if stripped.startswith("{"):
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            return {}
        if isinstance(data, dict):
            return {str(key): str(value) for key, value in data.items() if key != "runs"}
        return {}
    status: dict[str, str] = {}
    for line in stripped.splitlines():
        for part in line.strip().split():
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            status[key] = value
    return status


def _status_log_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path if path.exists() else None


def _read_json_file(path: Path) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _tail_file(path: Path, lines: int) -> str:
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
    except Exception:
        return ""


def _relative_path(path: Path | None) -> str:
    if path is None:
        return "暂无数据"
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _format_status_time(value: object | None) -> str:
    if value in {None, ""}:
        return "暂无数据"
    try:
        return _format_time(parse_datetime(str(value)))
    except Exception:
        return str(value)


def _format_mtime(path: Path) -> str:
    return _format_time(datetime.fromtimestamp(path.stat().st_mtime, tz=UTC))


def _format_bytes(value: int) -> str:
    units = [(1024 * 1024 * 1024, "GB"), (1024 * 1024, "MB"), (1024, "KB")]
    for divisor, suffix in units:
        if value >= divisor:
            return f"{value / divisor:.2f} {suffix}"
    return f"{value} B"


def _env_has_value(name: str) -> bool:
    env_path = PROJECT_ROOT / ".env"
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return False
    prefix = f"{name}="
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or not stripped.startswith(prefix):
            continue
        return bool(stripped[len(prefix) :].strip().strip("\"'"))
    return False


def _format_time(value: datetime | None) -> str:
    converted = to_new_york(value) if value else None
    return converted.strftime("%Y-%m-%d %H:%M %Z") if converted else "暂无数据"


def _format_decimal(value: Decimal | float | int | None, digits: int = 2) -> str:
    if value is None:
        return "暂无数据"
    return f"{float(value):,.{digits}f}"


def _format_money_compact(value: Decimal | float | int | None, currency: str | None = "USD") -> str:
    if value is None:
        return "暂无数据"
    number = float(value)
    absolute = abs(number)
    units = [(1_000_000_000_000, "T"), (1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")]
    for divisor, suffix in units:
        if absolute >= divisor:
            return f"{number / divisor:,.2f}{suffix} {currency or ''}".strip()
    return f"{number:,.2f} {currency or ''}".strip()


def _format_number_compact(value: Decimal | float | int | None) -> str:
    if value is None:
        return "暂无数据"
    return _format_money_compact(value, "").strip()


def _format_range(low: Decimal | None, high: Decimal | None) -> str:
    if low is None and high is None:
        return "暂无数据"
    return f"{_format_decimal(low)} - {_format_decimal(high)}"


def _format_money_range(low: Decimal | None, high: Decimal | None, currency: str | None) -> str:
    if low is None and high is None:
        return "暂无数据"
    return f"{_format_money_compact(low, currency)} - {_format_money_compact(high, currency)}"


def _to_float(value: Decimal | float | int | None) -> float | None:
    return float(value) if value is not None else None


def _missing(value: object | None) -> str:
    return str(value) if value not in {None, ""} else "暂无数据"


def _model_row(row: object) -> dict[str, object]:
    return {col.name: _jsonable(getattr(row, col.name)) for col in row.__table__.columns}


def _jsonable(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


if __name__ == "__main__":
    render()
