from __future__ import annotations

from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from finance_engine import (
    DataQualityReport,
    enrich_financial_data,
    enterprise_value_from_share_price,
    implied_growth_scenarios,
    normalize_financial_data,
    required_future_value,
    target_ev_from_equity_return,
    trailing_cagr,
)


APP_DIR = Path(__file__).resolve().parent
TEMPLATE_FILE = APP_DIR / "templates" / "financial_data_template.csv"

MONEY_COLUMNS = [
    "revenue",
    "gross_profit",
    "operating_income",
    "net_income",
    "operating_cash_flow",
    "capex",
    "free_cash_flow",
    "cash",
    "total_debt",
]

METRIC_LABELS = {
    "revenue": "营业收入",
    "gross_profit": "毛利润",
    "operating_income": "营业利润",
    "net_income": "净利润",
    "free_cash_flow": "自由现金流",
    "gross_margin": "毛利率",
    "operating_margin": "营业利润率",
    "net_margin": "净利率",
    "fcf_margin": "自由现金流率",
    "revenue_growth": "收入同比",
    "net_income_growth": "净利润同比",
    "fcf_growth": "自由现金流同比",
    "incremental_operating_margin": "增量营业利润率",
    "incremental_net_margin": "增量净利率",
    "incremental_fcf_margin": "增量自由现金流率",
    "growth_acceleration": "收入增长加速度",
    "rule_of_40": "Rule of 40",
}

PLOT_COLORS = ["#4F7BFF", "#21C7A8", "#FFB84D", "#F06B78", "#9A78F5"]


def main() -> None:
    st.set_page_config(
        page_title="企业财务与隐含估值分析",
        page_icon="◈",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _apply_style()
    _header()

    raw, source_label = _data_source()
    normalized, report = normalize_financial_data(raw)
    _show_quality_messages(report)
    if not report.ok:
        _empty_state()
        return

    all_data = enrich_financial_data(normalized)
    companies = all_data["company"].dropna().unique().tolist()
    if not companies:
        st.error("未找到有效公司。")
        return

    with st.sidebar:
        st.markdown("### 分析范围")
        company = st.selectbox("公司", companies)
        include_estimates = st.toggle("包含预测期", value=True)

    company_all = all_data[all_data["company"] == company].copy()
    company_data = company_all.copy()
    if not include_estimates:
        company_data = company_data[~company_data["is_estimate"]].copy()
    if company_data.empty:
        st.warning("当前筛选范围没有可分析数据，请打开“包含预测期”。")
        return

    latest = company_data.sort_values("fiscal_year").iloc[-1]
    ticker = latest["ticker"] or "未提供代码"
    st.caption(
        f"当前分析：{company} · {ticker} · 数据源：{source_label} · "
        f"金额单位：百万 {latest['currency']}"
    )

    tabs = st.tabs(["总览", "自动图表", "盈利速度", "估值反推", "数据与模板"])
    with tabs[0]:
        _overview(company_data)
    with tabs[1]:
        _charts(company_data)
    with tabs[2]:
        _profitability_speed(company_data)
    with tabs[3]:
        _valuation(company_data)
    with tabs[4]:
        _data_and_template(company_all, report)


def _header() -> None:
    st.markdown(
        """
        <section class="hero">
            <div class="eyebrow">FINANCIAL INTELLIGENCE</div>
            <h1>企业财务与隐含估值分析</h1>
            <p>上传年度财务数据，自动识别增长、利润率与现金流趋势，
            并反推当前企业价值或股价要求未来兑现什么。</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _data_source() -> tuple[pd.DataFrame, str]:
    with st.sidebar:
        st.markdown("### 数据")
        uploaded = st.file_uploader(
            "上传财务数据",
            type=["csv", "xlsx"],
            help="支持 UTF-8 CSV 或 Excel；Excel 默认读取第一个工作表。",
        )
        st.download_button(
            "下载上传模板",
            data=TEMPLATE_FILE.read_bytes(),
            file_name="financial_data_template.csv",
            mime="text/csv",
            width="stretch",
        )
        st.caption("未上传时使用内置示例。CSV 可直接用 Excel 打开。")

    if uploaded is None:
        return pd.read_csv(TEMPLATE_FILE), "内置示例"

    try:
        suffix = Path(uploaded.name).suffix.lower()
        payload = uploaded.getvalue()
        if suffix == ".csv":
            return _read_csv_bytes(payload), uploaded.name
        return pd.read_excel(BytesIO(payload), sheet_name=0), uploaded.name
    except ImportError:
        st.error("读取 Excel 需要 openpyxl，请先执行 `pip install -r requirements.txt`。")
    except Exception as exc:
        st.error(f"无法读取上传文件：{exc}")
    return pd.DataFrame(), uploaded.name


def _read_csv_bytes(payload: bytes) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return pd.read_csv(BytesIO(payload), encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error:
        raise last_error
    return pd.read_csv(BytesIO(payload))


def _show_quality_messages(report: DataQualityReport) -> None:
    for message in report.errors:
        st.error(message)
    for message in report.warnings:
        st.warning(message)


def _empty_state() -> None:
    st.info("请修正数据后重新上传。最少需要 company、fiscal_year、revenue 三列。")
    st.download_button(
        "下载标准模板",
        data=TEMPLATE_FILE.read_bytes(),
        file_name="financial_data_template.csv",
        mime="text/csv",
    )


def _overview(data: pd.DataFrame) -> None:
    revenue_row = _latest_metric_row(data, "revenue")
    operating_row = _latest_metric_row(data, "operating_margin")
    fcf_row = _latest_metric_row(data, "free_cash_flow")
    fcf_margin_row = _latest_metric_row(data, "fcf_margin")
    rule_row = _latest_metric_row(data, "rule_of_40")

    st.markdown("### 最新财年快照")
    columns = st.columns(5)
    columns[0].metric(
        f"营业收入 · {int(revenue_row['fiscal_year'])}",
        _money(revenue_row["revenue"], revenue_row["currency"]),
        _percent(revenue_row["revenue_growth"]),
    )
    columns[1].metric(
        f"营业利润率 · {int(operating_row['fiscal_year'])}",
        _percent(operating_row["operating_margin"]),
        _percentage_point_delta(
            operating_row,
            _previous_metric_row(data, "operating_margin"),
            "operating_margin",
        ),
    )
    columns[2].metric(
        f"自由现金流 · {int(fcf_row['fiscal_year'])}",
        _money(fcf_row["free_cash_flow"], fcf_row["currency"]),
        _percent(fcf_row["fcf_growth"]),
    )
    columns[3].metric(
        f"自由现金流率 · {int(fcf_margin_row['fiscal_year'])}",
        _percent(fcf_margin_row["fcf_margin"]),
        _percentage_point_delta(
            fcf_margin_row,
            _previous_metric_row(data, "fcf_margin"),
            "fcf_margin",
        ),
    )
    columns[4].metric(
        f"Rule of 40 · {int(rule_row['fiscal_year'])}",
        _percent(rule_row["rule_of_40"]),
    )

    st.markdown("### 增长与盈利是否同时兑现")
    left, right = st.columns([1.55, 1])
    with left:
        trend = data[
            ["fiscal_year", "revenue", "operating_income", "free_cash_flow", "is_estimate"]
        ].melt(
            id_vars=["fiscal_year", "is_estimate"],
            value_vars=["revenue", "operating_income", "free_cash_flow"],
            var_name="metric",
            value_name="value",
        )
        trend["metric"] = trend["metric"].map(METRIC_LABELS)
        trend["period"] = trend["is_estimate"].map({True: "预测", False: "实际"})
        fig = px.line(
            trend,
            x="fiscal_year",
            y="value",
            color="metric",
            line_dash="period",
            markers=True,
            color_discrete_sequence=PLOT_COLORS,
            labels={"fiscal_year": "财年", "value": "百万", "metric": ""},
        )
        _polish_chart(fig, "收入、营业利润与自由现金流")
        st.plotly_chart(fig, width="stretch")
    with right:
        _insight_panel(data)


def _insight_panel(data: pd.DataFrame) -> None:
    growth_row = _latest_metric_row(data, "revenue_growth")
    fcf_margin_row = _latest_metric_row(data, "fcf_margin")
    acceleration_row = _latest_metric_row(data, "growth_acceleration")
    revenue_cagr, cagr_years = trailing_cagr(data, "revenue", max_years=3)
    fcf_cagr, _ = trailing_cagr(data, "free_cash_flow", max_years=3)

    growth_signal = _signal(
        growth_row["revenue_growth"],
        [(0.30, "高速扩张", "good"), (0.10, "稳健扩张", "neutral")],
        "低速增长",
    )
    cash_signal = _signal(
        fcf_margin_row["fcf_margin"],
        [(0.25, "现金转化很强", "good"), (0.10, "现金转化健康", "neutral")],
        "现金转化偏弱",
    )
    acceleration = acceleration_row["growth_acceleration"]
    acceleration_text = (
        "增速仍在加快"
        if pd.notna(acceleration) and acceleration > 0
        else "增速正在放缓"
        if pd.notna(acceleration) and acceleration < 0
        else "增速大致稳定"
    )

    st.markdown(
        f"""
        <div class="insight-card">
          <div class="card-label">自动解读</div>
          <div class="signal-row"><span>增长</span><b>{growth_signal[0]}</b></div>
          <div class="signal-row"><span>现金流</span><b>{cash_signal[0]}</b></div>
          <div class="signal-row"><span>动量</span><b>{acceleration_text}</b></div>
          <hr>
          <p>近 {cagr_years} 年收入 CAGR <strong>{_percent(revenue_cagr)}</strong>；
          自由现金流 CAGR <strong>{_percent(fcf_cagr)}</strong>。</p>
          <p class="fine-print">判断基于上传数据，只描述经营趋势，不代表投资结论。</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _charts(data: pd.DataFrame) -> None:
    st.markdown("### 自动生成的经营图表")
    chart_1, chart_2 = st.columns(2)

    with chart_1:
        values = data[["fiscal_year", "is_estimate", *MONEY_COLUMNS[:5], "free_cash_flow"]]
        values = values.melt(
            id_vars=["fiscal_year", "is_estimate"],
            var_name="metric",
            value_name="value",
        ).dropna(subset=["value"])
        selected = st.multiselect(
            "选择金额指标",
            options=list(dict.fromkeys(values["metric"].tolist())),
            default=["revenue", "gross_profit", "operating_income", "free_cash_flow"],
            format_func=lambda value: METRIC_LABELS.get(value, value),
        )
        filtered = values[values["metric"].isin(selected)].copy()
        filtered["metric"] = filtered["metric"].map(METRIC_LABELS)
        filtered["period"] = filtered["is_estimate"].map({True: "预测", False: "实际"})
        fig = px.line(
            filtered,
            x="fiscal_year",
            y="value",
            color="metric",
            line_dash="period",
            markers=True,
            color_discrete_sequence=PLOT_COLORS,
            labels={"fiscal_year": "财年", "value": "百万", "metric": ""},
        )
        _polish_chart(fig, "经营规模趋势")
        st.plotly_chart(fig, width="stretch")

    with chart_2:
        margins = data[
            [
                "fiscal_year",
                "is_estimate",
                "gross_margin",
                "operating_margin",
                "net_margin",
                "fcf_margin",
            ]
        ].melt(
            id_vars=["fiscal_year", "is_estimate"],
            var_name="metric",
            value_name="value",
        )
        margins["metric"] = margins["metric"].map(METRIC_LABELS)
        margins["period"] = margins["is_estimate"].map({True: "预测", False: "实际"})
        fig = px.line(
            margins,
            x="fiscal_year",
            y="value",
            color="metric",
            line_dash="period",
            markers=True,
            color_discrete_sequence=PLOT_COLORS,
            labels={"fiscal_year": "财年", "value": "利润率", "metric": ""},
        )
        fig.update_yaxes(tickformat=".0%")
        _polish_chart(fig, "利润率演变")
        st.plotly_chart(fig, width="stretch")

    chart_3, chart_4 = st.columns(2)
    with chart_3:
        growth = data[
            ["fiscal_year", "revenue_growth", "growth_acceleration", "rule_of_40"]
        ].melt(id_vars="fiscal_year", var_name="metric", value_name="value")
        growth["metric"] = growth["metric"].map(METRIC_LABELS)
        fig = px.bar(
            growth,
            x="fiscal_year",
            y="value",
            color="metric",
            barmode="group",
            color_discrete_sequence=PLOT_COLORS,
            labels={"fiscal_year": "财年", "value": "比例", "metric": ""},
        )
        fig.update_yaxes(tickformat=".0%")
        _polish_chart(fig, "增长、加速度与 Rule of 40")
        st.plotly_chart(fig, width="stretch")

    with chart_4:
        balance = data[["fiscal_year", "cash", "total_debt"]].melt(
            id_vars="fiscal_year", var_name="metric", value_name="value"
        )
        balance["metric"] = balance["metric"].map(
            {"cash": "现金", "total_debt": "总债务"}
        )
        fig = px.bar(
            balance,
            x="fiscal_year",
            y="value",
            color="metric",
            barmode="group",
            color_discrete_sequence=["#21C7A8", "#F06B78"],
            labels={"fiscal_year": "财年", "value": "百万", "metric": ""},
        )
        _polish_chart(fig, "现金与债务")
        st.plotly_chart(fig, width="stretch")


def _profitability_speed(data: pd.DataFrame) -> None:
    growth_row = _latest_metric_row(data, "growth_acceleration")
    operating_row = _latest_metric_row(data, "incremental_operating_margin")
    fcf_row = _latest_metric_row(data, "incremental_fcf_margin")
    fcf_margin_row = _latest_metric_row(data, "fcf_margin")
    previous_fcf_margin_row = _previous_metric_row(data, "fcf_margin")
    revenue_cagr, cagr_years = trailing_cagr(data, "revenue", max_years=3)
    operating_cagr, _ = trailing_cagr(data, "operating_income", max_years=3)
    fcf_cagr, _ = trailing_cagr(data, "free_cash_flow", max_years=3)

    st.markdown("### 盈利速度拆解")
    st.caption(
        "不使用黑箱综合分数，而是把“规模扩张、增量利润、现金转化、增长动量”分别展示。"
    )
    columns = st.columns(4)
    columns[0].metric(f"收入 CAGR（{cagr_years} 年）", _percent(revenue_cagr))
    columns[1].metric(
        f"增量营业利润率 · {int(operating_row['fiscal_year'])}",
        _percent(operating_row["incremental_operating_margin"]),
    )
    columns[2].metric(
        f"增量自由现金流率 · {int(fcf_row['fiscal_year'])}",
        _percent(fcf_row["incremental_fcf_margin"]),
    )
    columns[3].metric(
        f"收入增长加速度 · {int(growth_row['fiscal_year'])}",
        _percentage_points(growth_row["growth_acceleration"]),
    )

    left, right = st.columns([1.35, 1])
    with left:
        incremental = data[
            [
                "fiscal_year",
                "incremental_operating_margin",
                "incremental_net_margin",
                "incremental_fcf_margin",
            ]
        ].melt(id_vars="fiscal_year", var_name="metric", value_name="value")
        incremental["metric"] = incremental["metric"].map(METRIC_LABELS)
        fig = px.bar(
            incremental,
            x="fiscal_year",
            y="value",
            color="metric",
            barmode="group",
            color_discrete_sequence=PLOT_COLORS,
            labels={"fiscal_year": "财年", "value": "增量利润 / 增量收入", "metric": ""},
        )
        fig.update_yaxes(tickformat=".0%")
        _polish_chart(fig, "每增加一元收入，新增多少利润和现金流")
        st.plotly_chart(fig, width="stretch")

    with right:
        first_op_profit = _first_positive_year(data, "operating_income")
        first_net_profit = _first_positive_year(data, "net_income")
        first_fcf_profit = _first_positive_year(data, "free_cash_flow")
        st.markdown("#### 盈利里程碑")
        milestones = pd.DataFrame(
            [
                {"里程碑": "营业利润转正", "首次年份": first_op_profit},
                {"里程碑": "净利润转正", "首次年份": first_net_profit},
                {"里程碑": "自由现金流转正", "首次年份": first_fcf_profit},
            ]
        )
        st.dataframe(milestones, hide_index=True, width="stretch")
        st.markdown("#### 速度判断")
        bullets = _profitability_bullets(
            operating_row=operating_row,
            fcf_row=fcf_row,
            fcf_margin_row=fcf_margin_row,
            previous_fcf_margin_row=previous_fcf_margin_row,
            revenue_cagr=revenue_cagr,
            operating_cagr=operating_cagr,
            fcf_cagr=fcf_cagr,
        )
        for bullet in bullets:
            st.markdown(f"- {bullet}")


def _valuation(data: pd.DataFrame) -> None:
    latest = data.sort_values("fiscal_year").iloc[-1]
    latest_revenue_b = max(float(latest["revenue"]) / 1_000, 0.01)
    latest_year = int(latest["fiscal_year"])

    st.markdown("### 当前估值隐含了什么")
    st.caption(
        "先按要求回报率求目标终值，再用终值 FCF 倍数和 FCF 率反推所需收入与 CAGR。"
    )

    mode = st.radio(
        "估值起点",
        ["直接输入当前企业价值", "由当前股价推导"],
        horizontal=True,
    )
    assumption_left, assumption_right = st.columns(2)

    with assumption_left:
        st.markdown("#### 回报与时间")
        required_return_pct = st.number_input(
            "投资者要求年化回报（%）",
            min_value=0.0,
            max_value=100.0,
            value=10.0,
            step=0.5,
        )
        holding_years = st.number_input(
            "从现在到退出的持有年数",
            min_value=0.1,
            max_value=30.0,
            value=4.44,
            step=0.1,
            help="Palantir 示例按约 4.44 年计算，因此 3,080 亿美元约增长到 4,700 亿美元。",
        )
        base_year = st.number_input(
            "收入基期年份",
            min_value=2000,
            max_value=2099,
            value=latest_year,
            step=1,
        )
        target_year = st.number_input(
            "终值年份",
            min_value=int(base_year) + 1,
            max_value=2100,
            value=max(2030, int(base_year) + 1),
            step=1,
        )
        growth_years = float(target_year - base_year)

    with assumption_right:
        st.markdown("#### 经营与终值")
        base_revenue_b = st.number_input(
            "基期收入（十亿美元）",
            min_value=0.01,
            value=round(latest_revenue_b, 2),
            step=0.1,
        )
        terminal_fcf_margin_pct = st.number_input(
            f"{int(target_year)} 年自由现金流率（%）",
            min_value=1.0,
            max_value=90.0,
            value=45.0,
            step=1.0,
        )
        multiples = st.multiselect(
            f"{int(target_year)} 年终值 FCF 倍数",
            options=list(range(10, 61, 5)),
            default=[20, 25, 30],
        )

    required_return = required_return_pct / 100
    terminal_fcf_margin = terminal_fcf_margin_pct / 100

    current_equity_value_b: float | None = None
    if mode == "直接输入当前企业价值":
        current_ev_b = st.number_input(
            "当前企业价值 EV（十亿美元）",
            min_value=0.1,
            value=308.0,
            step=1.0,
        )
        target_ev_b = required_future_value(current_ev_b, required_return, holding_years)
        bridge_note = (
            "简化口径：直接将 EV 按要求回报率复利，隐含净债务变化不影响股东回报。"
        )
    else:
        bridge_1, bridge_2, bridge_3, bridge_4 = st.columns(4)
        share_price = bridge_1.number_input(
            "当前股价",
            min_value=0.01,
            value=_positive_or_default(latest["share_price"], 100.0),
            step=1.0,
        )
        diluted_shares_m = bridge_2.number_input(
            "稀释后股数（百万股）",
            min_value=0.01,
            value=_positive_or_default(latest["diluted_shares"], 2_500.0),
            step=10.0,
        )
        cash_m = bridge_3.number_input(
            "当前现金（百万）",
            min_value=0.0,
            value=_nonnegative_or_default(latest["cash"], 0.0),
            step=100.0,
        )
        debt_m = bridge_4.number_input(
            "当前债务（百万）",
            min_value=0.0,
            value=_nonnegative_or_default(latest["total_debt"], 0.0),
            step=100.0,
        )
        current_equity_value_b, current_ev_b = enterprise_value_from_share_price(
            share_price=share_price,
            diluted_shares_m=diluted_shares_m,
            cash_m=cash_m,
            debt_m=debt_m,
        )
        terminal_net_debt_b = st.number_input(
            f"{int(target_year)} 年预计净债务（债务−现金，十亿美元）",
            value=round((debt_m - cash_m) / 1_000, 2),
            step=0.5,
        )
        target_equity_b, target_ev_b = target_ev_from_equity_return(
            current_equity_value_b=current_equity_value_b,
            required_return=required_return,
            holding_years=holding_years,
            terminal_net_debt_b=terminal_net_debt_b,
        )
        bridge_note = (
            f"权益桥：当前权益价值 ${current_equity_value_b:.1f}B，"
            f"要求退出权益价值 ${target_equity_b:.1f}B；再加终值净债务得到目标 EV。"
        )

    st.info(bridge_note)
    top = st.columns(3)
    top[0].metric("当前企业价值", f"${current_ev_b:,.1f}B")
    top[1].metric(f"{int(target_year)} 所需企业价值", f"${target_ev_b:,.1f}B")
    top[2].metric("所需估值增幅", f"{target_ev_b / current_ev_b - 1:.1%}")

    if not multiples:
        st.warning("请至少选择一个终值 FCF 倍数。")
        return

    scenarios = implied_growth_scenarios(
        target_enterprise_value=target_ev_b,
        terminal_fcf_margin=terminal_fcf_margin,
        base_revenue=base_revenue_b,
        growth_years=growth_years,
        terminal_multiples=multiples,
    )
    display = scenarios.rename(
        columns={
            "terminal_fcf_multiple": "终值 FCF 倍数",
            "required_fcf": "所需自由现金流（十亿美元）",
            "required_revenue": "所需收入（十亿美元）",
            "implied_revenue_cagr": "隐含收入 CAGR",
        }
    ).copy()
    display["终值 FCF 倍数"] = display["终值 FCF 倍数"].map(lambda value: f"{value:.0f}x")
    display["隐含收入 CAGR"] *= 100

    st.markdown("#### 反推结果")
    st.dataframe(
        display,
        hide_index=True,
        width="stretch",
        column_config={
            "所需自由现金流（十亿美元）": st.column_config.NumberColumn(format="$%.1f"),
            "所需收入（十亿美元）": st.column_config.NumberColumn(format="$%.1f"),
            "隐含收入 CAGR": st.column_config.NumberColumn(format="%.1f%%"),
        },
    )

    _valuation_callout(
        scenarios=scenarios,
        target_year=int(target_year),
        terminal_fcf_margin=terminal_fcf_margin,
    )
    _valuation_sensitivity(
        target_ev_b=target_ev_b,
        base_revenue_b=base_revenue_b,
        growth_years=growth_years,
        multiples=multiples,
    )


def _valuation_callout(
    *, scenarios: pd.DataFrame, target_year: int, terminal_fcf_margin: float
) -> None:
    selected = scenarios.iloc[-1]
    multiple = selected["terminal_fcf_multiple"]
    cagr = selected["implied_revenue_cagr"]
    st.markdown(
        f"""
        <div class="thesis-card">
          <div class="card-label">市场隐含条件 · 乐观倍数情景</div>
          <h3>即使给予 {multiple:.0f}x 终值 FCF，收入仍需年均增长 {cagr:.1%}</h3>
          <p>当前估值要求以下条件同时满足：</p>
          <ol>
            <li>收入从基期到 {target_year} 年平均增长约 <strong>{cagr:.1%}</strong>；</li>
            <li>{target_year} 年自由现金流率达到或保持 <strong>{terminal_fcf_margin:.0%}</strong>；</li>
            <li>{target_year} 年市场仍愿意给予 <strong>{multiple:.0f}x FCF</strong>。</li>
          </ol>
          <p class="fine-print">这不是盈利预测，而是把当前价格背后的必要条件显性化。</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _valuation_sensitivity(
    *,
    target_ev_b: float,
    base_revenue_b: float,
    growth_years: float,
    multiples: list[int],
) -> None:
    margins = [0.30, 0.35, 0.40, 0.45, 0.50]
    z: list[list[float]] = []
    for margin in margins:
        row = implied_growth_scenarios(
            target_enterprise_value=target_ev_b,
            terminal_fcf_margin=margin,
            base_revenue=base_revenue_b,
            growth_years=growth_years,
            terminal_multiples=multiples,
        )
        z.append((row["implied_revenue_cagr"] * 100).tolist())

    heatmap = go.Figure(
        data=go.Heatmap(
            z=z,
            x=[f"{multiple}x" for multiple in multiples],
            y=[f"{margin:.0%}" for margin in margins],
            colorscale=[
                [0.0, "#163B49"],
                [0.5, "#4F7BFF"],
                [1.0, "#F06B78"],
            ],
            text=[[f"{value:.1f}%" for value in row] for row in z],
            texttemplate="%{text}",
            hovertemplate="FCF 倍数 %{x}<br>FCF 率 %{y}<br>隐含 CAGR %{text}<extra></extra>",
            colorbar={"title": "CAGR"},
        )
    )
    heatmap.update_layout(
        title="终值倍数 × FCF 率：隐含收入 CAGR",
        xaxis_title="终值 FCF 倍数",
        yaxis_title="终值自由现金流率",
    )
    _polish_chart(heatmap, None)
    st.plotly_chart(heatmap, width="stretch")


def _data_and_template(data: pd.DataFrame, report: DataQualityReport) -> None:
    st.markdown("### 数据检查与导出")
    status_cols = st.columns(4)
    status_cols[0].metric("数据行", f"{len(data)}")
    status_cols[1].metric("财年数", f"{data['fiscal_year'].nunique()}")
    status_cols[2].metric("预测行", f"{int(data['is_estimate'].sum())}")
    status_cols[3].metric("自动补算 FCF", f"{report.filled_fcf_rows} 行")

    display = data.copy()
    for column in [
        "revenue_growth",
        "gross_margin",
        "operating_margin",
        "net_margin",
        "fcf_margin",
        "incremental_operating_margin",
        "incremental_net_margin",
        "incremental_fcf_margin",
        "growth_acceleration",
        "rule_of_40",
    ]:
        display[column] = display[column] * 100
    st.dataframe(
        display,
        hide_index=True,
        width="stretch",
        column_config={
            column: st.column_config.NumberColumn(
                METRIC_LABELS.get(column, column), format="%.1f%%"
            )
            for column in [
                "revenue_growth",
                "gross_margin",
                "operating_margin",
                "net_margin",
                "fcf_margin",
                "incremental_operating_margin",
                "incremental_net_margin",
                "incremental_fcf_margin",
                "growth_acceleration",
                "rule_of_40",
            ]
        },
    )
    st.download_button(
        "下载含计算指标的数据",
        data=display.to_csv(index=False).encode("utf-8-sig"),
        file_name="financial_analysis_output.csv",
        mime="text/csv",
    )

    st.markdown("### 上传模板")
    template_left, template_right = st.columns([1, 1.6])
    with template_left:
        st.download_button(
            "下载 CSV 模板",
            data=TEMPLATE_FILE.read_bytes(),
            file_name="financial_data_template.csv",
            mime="text/csv",
            type="primary",
        )
        st.caption("UTF-8 编码，可直接用 Excel 打开编辑。")
    with template_right:
        st.markdown(
            """
            - 金额列统一使用“百万”；股价使用每股价格。
            - `capex` 填正数绝对值；FCF 留空时自动按 OCF − Capex 补算。
            - `is_estimate` 填 `true/false`，用于区分实绩和预测。
            - 最少需要 `company`、`fiscal_year`、`revenue`。
            """
        )

    with st.expander("字段定义"):
        definitions = pd.DataFrame(
            [
                ("company", "公司名称", "必填"),
                ("ticker", "股票代码", "可选"),
                ("fiscal_year", "财年，例如 2026", "必填"),
                ("revenue", "营业收入，百万", "必填"),
                ("gross_profit", "毛利润，百万", "建议"),
                ("operating_income", "营业利润，百万", "建议"),
                ("net_income", "净利润，百万", "建议"),
                ("operating_cash_flow", "经营现金流，百万", "建议"),
                ("capex", "资本开支正数绝对值，百万", "建议"),
                ("free_cash_flow", "自由现金流，百万；可留空自动计算", "建议"),
                ("cash / total_debt", "现金 / 总债务，百万", "估值桥需要"),
                ("diluted_shares", "稀释后股数，百万股", "股价模式需要"),
                ("share_price", "每股价格", "股价模式需要"),
                ("currency", "币种，例如 USD", "可选"),
                ("is_estimate", "是否为预测期 true/false", "可选"),
                ("source_note", "数据口径、是否为公司指引等说明", "建议"),
                ("source_url", "原始披露或数据来源链接", "建议"),
            ],
            columns=["字段", "定义", "要求"],
        )
        st.dataframe(definitions, hide_index=True, width="stretch")


def _profitability_bullets(
    *,
    operating_row: pd.Series,
    fcf_row: pd.Series,
    fcf_margin_row: pd.Series,
    previous_fcf_margin_row: pd.Series | None,
    revenue_cagr: float,
    operating_cagr: float,
    fcf_cagr: float,
) -> list[str]:
    bullets = [
        f"规模扩张：近年收入 CAGR 为 {_percent(revenue_cagr)}。",
        (
            f"利润放大：营业利润 CAGR 为 {_percent(operating_cagr)}，"
            f"最新增量营业利润率为 "
            f"{_percent(operating_row['incremental_operating_margin'])}。"
        ),
        (
            f"现金兑现：自由现金流 CAGR 为 {_percent(fcf_cagr)}，"
            f"最新增量自由现金流率为 "
            f"{_percent(fcf_row['incremental_fcf_margin'])}。"
        ),
    ]
    if previous_fcf_margin_row is not None:
        margin_change = (
            fcf_margin_row["fcf_margin"] - previous_fcf_margin_row["fcf_margin"]
        )
        direction = "提升" if margin_change > 0 else "下降" if margin_change < 0 else "持平"
        bullets.append(
            f"盈利质量：自由现金流率同比{direction} {_percentage_points(abs(margin_change))}。"
        )
    return bullets


def _first_positive_year(data: pd.DataFrame, column: str) -> str:
    positive = data[data[column] > 0].sort_values("fiscal_year")
    if positive.empty:
        return "尚未转正"
    row = positive.iloc[0]
    suffix = "（预测）" if bool(row["is_estimate"]) else ""
    return f"{int(row['fiscal_year'])}{suffix}"


def _latest_metric_row(data: pd.DataFrame, column: str) -> pd.Series:
    available = data.dropna(subset=[column]).sort_values("fiscal_year")
    if available.empty:
        return data.sort_values("fiscal_year").iloc[-1]
    return available.iloc[-1]


def _previous_metric_row(data: pd.DataFrame, column: str) -> pd.Series | None:
    available = data.dropna(subset=[column]).sort_values("fiscal_year")
    if len(available) < 2:
        return None
    return available.iloc[-2]


def _signal(
    value: float,
    thresholds: list[tuple[float, str, str]],
    fallback: str,
) -> tuple[str, str]:
    if pd.isna(value):
        return "数据不足", "neutral"
    for threshold, label, tone in thresholds:
        if value >= threshold:
            return label, tone
    return fallback, "warning"


def _polish_chart(fig: go.Figure, title: str | None) -> None:
    fig.update_layout(
        title=title,
        height=420,
        margin={"l": 12, "r": 12, "t": 54 if title else 30, "b": 12},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend={"orientation": "h", "y": -0.18, "x": 0},
        hovermode="x unified",
    )
    fig.update_xaxes(showgrid=False, dtick=1)
    fig.update_yaxes(gridcolor="rgba(130,145,170,0.16)", zerolinecolor="rgba(130,145,170,0.3)")


def _money(value: object, currency: object = "USD") -> str:
    if pd.isna(value):
        return "—"
    symbol = "$" if str(currency).upper() == "USD" else f"{currency} "
    return f"{symbol}{float(value):,.0f}M"


def _percent(value: object) -> str:
    if pd.isna(value) or np.isinf(value):
        return "—"
    return f"{float(value):.1%}"


def _percentage_points(value: object) -> str:
    if pd.isna(value) or np.isinf(value):
        return "—"
    return f"{float(value) * 100:.1f} 个百分点"


def _percentage_point_delta(
    latest: pd.Series, previous: pd.Series | None, column: str
) -> str | None:
    if previous is None or pd.isna(latest[column]) or pd.isna(previous[column]):
        return None
    delta = float(latest[column]) - float(previous[column])
    return f"{delta * 100:+.1f} 个百分点"


def _positive_or_default(value: object, default: float) -> float:
    if pd.isna(value) or float(value) <= 0:
        return default
    return float(value)


def _nonnegative_or_default(value: object, default: float) -> float:
    if pd.isna(value) or float(value) < 0:
        return default
    return float(value)


def _apply_style() -> None:
    st.markdown(
        """
        <style>
        :root {
          --ink: #172033;
          --muted: #65708a;
          --line: rgba(79, 123, 255, 0.16);
          --blue: #4f7bff;
          --mint: #21c7a8;
        }
        .stApp {
          background:
            radial-gradient(circle at 78% 2%, rgba(79,123,255,.10), transparent 28rem),
            radial-gradient(circle at 9% 18%, rgba(33,199,168,.07), transparent 24rem);
        }
        .block-container { padding-top: 2rem; max-width: 1480px; }
        .hero {
          border: 1px solid var(--line);
          border-radius: 24px;
          padding: 28px 32px;
          margin-bottom: 22px;
          background: linear-gradient(135deg, rgba(79,123,255,.12), rgba(33,199,168,.06));
          box-shadow: 0 18px 52px rgba(28, 45, 80, .08);
        }
        .hero h1 { margin: 4px 0 8px; font-size: clamp(2rem, 4vw, 3.7rem); letter-spacing: -.045em; }
        .hero p { max-width: 850px; color: var(--muted); font-size: 1.06rem; margin: 0; line-height: 1.7; }
        .eyebrow, .card-label {
          color: var(--blue);
          font-size: .74rem;
          letter-spacing: .16em;
          font-weight: 800;
        }
        div[data-testid="stMetric"] {
          border: 1px solid var(--line);
          border-radius: 18px;
          padding: 16px 18px;
          background: rgba(255,255,255,.54);
          box-shadow: 0 8px 28px rgba(35, 55, 95, .055);
        }
        div[data-testid="stMetricValue"] { font-weight: 720; letter-spacing: -.03em; }
        .insight-card, .thesis-card {
          border: 1px solid var(--line);
          border-radius: 20px;
          padding: 22px;
          background: rgba(255,255,255,.58);
          min-height: 340px;
        }
        .thesis-card { min-height: 0; margin: 18px 0; }
        .thesis-card h3 { margin: 8px 0 14px; font-size: 1.35rem; }
        .signal-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 12px 0;
          border-bottom: 1px solid rgba(100,120,150,.12);
        }
        .signal-row span { color: var(--muted); }
        .fine-print { color: var(--muted); font-size: .84rem; }
        [data-testid="stSidebar"] { border-right: 1px solid rgba(100,120,150,.14); }
        [data-testid="stSidebar"] .block-container { padding-top: 2rem; }
        .stTabs [data-baseweb="tab-list"] { gap: 8px; }
        .stTabs [data-baseweb="tab"] {
          border-radius: 12px;
          padding: 8px 16px;
          border: 1px solid rgba(100,120,150,.14);
        }
        @media (prefers-color-scheme: dark) {
          :root { --ink: #eef3ff; --muted: #aab6cf; --line: rgba(113,148,255,.23); }
          div[data-testid="stMetric"], .insight-card, .thesis-card {
            background: rgba(14,22,38,.56);
          }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
