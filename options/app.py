from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from option_math import (
    OptionLeg,
    aggregate_score,
    black_scholes,
    breakeven,
    dte,
    implied_volatility,
    scenario_matrix,
    score_delta,
    score_dte,
    score_iv_rank,
    score_theta_pct,
    score_vega_pct,
    required_spot_for_premium,
    strategy_metrics,
    theta_pct,
    vega_pct,
)
from storage import (
    ACCOUNT_SNAPSHOTS_FILE,
    REVIEWS_FILE,
    TRADES_FILE,
    append_account_snapshot,
    append_review,
    append_trade,
    compute_positions,
    contract_key,
    load_account_snapshots,
    load_reviews,
    load_trades,
    save_account_snapshots,
    save_reviews,
    save_trades,
)


STATUS_LABEL = {"green": "健康", "yellow": "警戒", "red": "危险"}
STATUS_COLOR = {"green": "#0f7a3b", "yellow": "#a15c00", "red": "#b42318"}


def main() -> None:
    st.set_page_config(page_title="期权工作台", layout="wide")
    _style()
    st.title("期权工作台")

    trades = load_trades()
    account_snapshots = load_account_snapshots()
    positions, realized = compute_positions(trades)

    tabs = st.tabs(["持仓", "账户资金", "买入计划", "卖出计划", "策略组合", "交易记录", "复盘看板"])
    with tabs[0]:
        _positions_page(trades, positions, realized)
    with tabs[1]:
        _account_page(account_snapshots, positions, realized)
    with tabs[2]:
        _buy_page(account_snapshots)
    with tabs[3]:
        _short_option_page(account_snapshots)
    with tabs[4]:
        _strategy_page()
    with tabs[5]:
        _trades_page(trades, realized)
    with tabs[6]:
        _review_page(positions, realized, trades)


def _positions_page(trades: pd.DataFrame, positions: pd.DataFrame, realized: pd.DataFrame) -> None:
    realized_total = float(realized["realized_pnl"].sum()) if not realized.empty else 0.0
    open_cost = float((positions["contracts"] * positions["avg_price"] * 100).sum()) if not positions.empty else 0.0
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("未平仓合约", int(positions["contracts"].sum()) if not positions.empty else 0)
    col2.metric("持仓成本/权利金", _money(open_cost))
    col3.metric("已实现盈亏", _money(realized_total))
    col4.metric("交易笔数", len(trades))

    if positions.empty:
        st.info("暂无未平仓期权。")
        return

    display = positions.copy()
    display["到期日"] = pd.to_datetime(display["expiry"], errors="coerce").dt.date
    display["DTE"] = display["到期日"].apply(lambda value: dte(value) if pd.notna(value) else 0)
    display["合约"] = display["contract_key"]
    display["方向"] = display["direction"]
    display["均价"] = display["avg_price"].map(lambda value: _money(value))
    display["成本/信用"] = (display["contracts"] * display["avg_price"] * 100).map(_money)
    st.subheader("当前持仓")
    st.dataframe(
        display[["合约", "方向", "contracts", "DTE", "均价", "成本/信用", "last_spot", "last_iv", "strategy", "tags"]],
        width="stretch",
        hide_index=True,
    )

    st.subheader("按当前权利金估值")
    mark_rows = []
    for _, row in positions.iterrows():
        mark_rows.append(
            {
                "合约": row["contract_key"],
                "方向": row["direction"],
                "张数": int(row["contracts"]),
                "均价": float(row["avg_price"]),
                "当前权利金": float(row["avg_price"]),
            }
        )
    marks = st.data_editor(pd.DataFrame(mark_rows), width="stretch", hide_index=True, key="position_marks")
    if not marks.empty:
        marks["未实现盈亏"] = marks.apply(
            lambda row: (
                (float(row["当前权利金"]) - float(row["均价"]))
                if row["方向"] == "long"
                else (float(row["均价"]) - float(row["当前权利金"]))
            )
            * int(row["张数"])
            * 100,
            axis=1,
        )
        st.metric("估算未实现盈亏", _money(float(marks["未实现盈亏"].sum())))
        st.dataframe(marks, width="stretch", hide_index=True)


def _account_page(account_snapshots: pd.DataFrame, positions: pd.DataFrame, realized: pd.DataFrame) -> None:
    st.subheader("账户资金")
    open_cost = float((positions["contracts"] * positions["avg_price"] * 100).sum()) if not positions.empty else 0.0
    realized_total = float(realized["realized_pnl"].sum()) if not realized.empty else 0.0
    latest = _latest_account_snapshot(account_snapshots)

    c1, c2, c3, c4 = st.columns(4)
    if latest is None:
        c1.metric("账户净值", "暂无")
        c2.metric("现金余额", "暂无")
        c3.metric("可用购买力", "暂无")
        c4.metric("期权成本占比", "暂无")
    else:
        net_liq = float(latest["net_liq"])
        cash = float(latest["cash"])
        buying_power = float(latest["buying_power"])
        exposure_pct = open_cost / net_liq * 100 if net_liq else 0.0
        c1.metric("账户净值", _money(net_liq))
        c2.metric("现金余额", _money(cash))
        c3.metric("可用购买力", _money(buying_power))
        c4.metric("期权成本占比", f"{exposure_pct:.1f}%")

    _close_position_with_account_form(account_snapshots, positions)

    with st.expander("新增账户快照", expanded=account_snapshots.empty):
        default_net_liq = _latest_account_size(account_snapshots)
        with st.form("account_snapshot_form"):
            c1, c2, c3, c4 = st.columns(4)
            record_date = c1.date_input("记录日期", value=date.today())
            account = c2.text_input("账户", value="主账户")
            net_liq = c3.number_input("账户净值", min_value=0.0, value=float(default_net_liq), step=100.0)
            cash = c4.number_input("现金余额", min_value=0.0, value=0.0, step=100.0)

            c1, c2, c3, c4 = st.columns(4)
            buying_power = c1.number_input("可用购买力", min_value=0.0, value=0.0, step=100.0)
            margin_used = c2.number_input("占用资金/保证金", min_value=0.0, value=0.0, step=100.0)
            deposit = c3.number_input("入金", min_value=0.0, value=0.0, step=100.0)
            withdrawal = c4.number_input("出金", min_value=0.0, value=0.0, step=100.0)

            realized_pnl = st.number_input("当日已实现盈亏", value=0.0, step=10.0)
            notes = st.text_area("备注", height=80)
            if st.form_submit_button("保存账户快照", type="primary"):
                append_account_snapshot(
                    {
                        "record_date": record_date.isoformat(),
                        "account": account,
                        "net_liq": net_liq,
                        "cash": cash,
                        "buying_power": buying_power,
                        "margin_used": margin_used,
                        "deposit": deposit,
                        "withdrawal": withdrawal,
                        "realized_pnl": realized_pnl,
                        "notes": notes,
                    }
                )
                st.success("已保存。")
                st.rerun()

    if account_snapshots.empty:
        st.info("暂无账户资金记录。建议每天收盘后或交易结束后记录一次账户快照。")
        return

    display = account_snapshots.copy()
    display["record_date_dt"] = pd.to_datetime(display["record_date"], errors="coerce")
    display = display.sort_values(["record_date_dt", "created_at"], ascending=[True, True])
    display["资金净流入"] = display["deposit"] - display["withdrawal"]

    st.subheader("账户曲线")
    chart_df = display.dropna(subset=["record_date_dt"])
    if not chart_df.empty:
        st.plotly_chart(px.line(chart_df, x="record_date_dt", y="net_liq", color="account", markers=True), width="stretch")
        flow_df = chart_df[chart_df["资金净流入"] != 0]
        if not flow_df.empty:
            st.plotly_chart(px.bar(flow_df, x="record_date_dt", y="资金净流入", color="account"), width="stretch")

    c1, c2, c3, c4 = st.columns(4)
    latest_net_liq = float(display.iloc[-1]["net_liq"])
    first_net_liq = float(display.iloc[0]["net_liq"])
    net_flow = float(display["资金净流入"].sum())
    account_pnl = latest_net_liq - first_net_liq - net_flow
    c1.metric("期初净值", _money(first_net_liq))
    c2.metric("最新净值", _money(latest_net_liq))
    c3.metric("累计净流入", _money(net_flow))
    c4.metric("账户口径盈亏", _money(account_pnl))

    table = display.drop(columns=["record_date_dt"]).sort_values(["record_date", "created_at"], ascending=False)
    st.subheader("资金记录")
    st.dataframe(table, width="stretch", hide_index=True)
    st.download_button("导出账户资金 CSV", data=account_snapshots.to_csv(index=False).encode("utf-8"), file_name="options_account_snapshots.csv")
    delete_id = st.selectbox("删除账户快照 ID", [""] + account_snapshots["id"].tolist())
    if delete_id and st.button("删除所选账户快照"):
        save_account_snapshots(account_snapshots[account_snapshots["id"] != delete_id])
        st.success("已删除。")
        st.rerun()


def _close_position_with_account_form(account_snapshots: pd.DataFrame, positions: pd.DataFrame) -> None:
    st.subheader("持仓卖出并同步资金")
    if positions.empty:
        st.info("暂无可卖出的持仓。")
        return

    latest = _latest_account_snapshot(account_snapshots)
    latest_account = str(latest["account"]) if latest is not None and str(latest["account"]).strip() else "主账户"
    latest_net_liq = float(latest["net_liq"]) if latest is not None else 0.0
    latest_cash = float(latest["cash"]) if latest is not None else 0.0
    latest_buying_power = float(latest["buying_power"]) if latest is not None else 0.0
    latest_margin_used = float(latest["margin_used"]) if latest is not None else 0.0

    labels = positions["contract_key"].tolist()
    selected = st.selectbox("选择要平仓的持仓", labels, key="close_position_select")
    position = positions[positions["contract_key"] == selected].iloc[0]
    direction = str(position["direction"])
    action = "卖出平仓" if direction == "long" else "买入平仓"

    with st.form("close_position_account_form"):
        c1, c2, c3, c4 = st.columns(4)
        close_date = c1.date_input("平仓日期", value=date.today(), key="close_trade_date")
        close_contracts = c2.number_input(
            "平仓张数",
            min_value=1,
            max_value=int(position["contracts"]),
            value=int(position["contracts"]),
            step=1,
        )
        close_premium = c3.number_input("卖出/平仓权利金", min_value=0.0, value=float(position["avg_price"]), step=0.01)
        fees = c4.number_input("手续费", min_value=0.0, value=0.0, step=0.1, key="close_trade_fees")

        c1, c2, c3, c4 = st.columns(4)
        spot = c1.number_input("标的价格", min_value=0.0, value=float(position["last_spot"]), step=0.01, key="close_trade_spot")
        iv = c2.number_input("IV %", min_value=0.0, value=float(position["last_iv"]), step=0.1, key="close_trade_iv")
        account = c3.text_input("同步账户", value=latest_account)
        sync_account = c4.checkbox("同步到账户资金", value=True)

        qty = int(close_contracts)
        avg_price = float(position["avg_price"])
        basis = avg_price * qty * 100
        if direction == "long":
            cash_delta = close_premium * qty * 100 - fees
            close_pnl = (close_premium - avg_price) * qty * 100 - fees
        else:
            cash_delta = -(close_premium * qty * 100 + fees)
            close_pnl = (avg_price - close_premium) * qty * 100 - fees
        pnl_pct = close_pnl / basis * 100 if basis else 0.0
        default_net_liq = max(0.0, latest_net_liq + close_pnl)
        default_cash = max(0.0, latest_cash + cash_delta)
        default_buying_power = max(0.0, latest_buying_power + cash_delta)
        default_margin_used = max(0.0, latest_margin_used - basis)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("动作", action)
        c2.metric("本次盈亏", _money(close_pnl), f"{pnl_pct:+.1f}%")
        c3.metric("现金变化", _money(cash_delta))
        c4.metric("成本基准", _money(basis))

        if sync_account:
            c1, c2, c3, c4 = st.columns(4)
            snapshot_net_liq = c1.number_input("同步后账户净值", min_value=0.0, value=float(default_net_liq), step=100.0)
            snapshot_cash = c2.number_input("同步后现金余额", min_value=0.0, value=float(default_cash), step=100.0)
            snapshot_buying_power = c3.number_input("同步后购买力", min_value=0.0, value=float(default_buying_power), step=100.0)
            snapshot_margin_used = c4.number_input("同步后占用资金", min_value=0.0, value=float(default_margin_used), step=100.0)
        else:
            snapshot_net_liq = latest_net_liq
            snapshot_cash = latest_cash
            snapshot_buying_power = latest_buying_power
            snapshot_margin_used = latest_margin_used

        notes = st.text_input("资金备注", value=f"{selected} {action} {qty} 张，权利金 {_money(close_premium)}")
        submitted = st.form_submit_button("保存平仓并同步", type="primary")

    if submitted:
        st.session_state["buy_calc_ready"] = True
    if not st.session_state.get("buy_calc_ready"):
        return

    append_trade(
        {
            "trade_date": close_date.isoformat(),
            "ticker": position["ticker"],
            "option_type": position["option_type"],
            "expiry": position["expiry"],
            "strike": position["strike"],
            "action": action,
            "contracts": qty,
            "premium": close_premium,
            "spot": spot,
            "iv": iv,
            "fees": fees,
            "strategy": position["strategy"],
            "thesis": "",
            "tags": position["tags"],
        }
    )
    if sync_account:
        append_account_snapshot(
            {
                "record_date": close_date.isoformat(),
                "account": account,
                "net_liq": snapshot_net_liq,
                "cash": snapshot_cash,
                "buying_power": snapshot_buying_power,
                "margin_used": snapshot_margin_used,
                "deposit": 0,
                "withdrawal": 0,
                "realized_pnl": close_pnl,
                "notes": notes,
            }
        )
    st.success("已保存平仓记录。")
    st.rerun()


def _buy_page(account_snapshots: pd.DataFrame) -> None:
    st.subheader("买入计划")
    account_default = _latest_account_size(account_snapshots)
    with st.form("buy_calc_form"):
        c1, c2, c3, c4 = st.columns(4)
        ticker = c1.text_input("标的", value="PLTR").upper()
        option_type_label = c2.selectbox("类型", ["PUT", "CALL"], index=0)
        expiry = c3.date_input("到期日", value=date.today() + timedelta(days=45))
        account_size = c4.number_input("账户总额", min_value=0.0, value=float(account_default), step=1000.0)

        c1, c2, c3, c4 = st.columns(4)
        spot = c1.number_input("标的现价", min_value=0.01, value=142.0, step=0.01)
        strike = c2.number_input("行权价", min_value=0.01, value=140.0, step=0.5)
        ask = c3.number_input("Ask/买入权利金", min_value=0.01, value=4.5, step=0.01)
        contracts = c4.number_input("计划张数", min_value=1, value=1, step=1)

        c1, c2, c3, c4 = st.columns(4)
        iv = c1.number_input("IV %", min_value=0.1, value=55.0, step=0.1)
        rate = c2.number_input("无风险利率 %", value=4.3, step=0.01)
        iv_rank = c3.slider("IV Rank", min_value=0, max_value=100, value=65)
        target_move = c4.number_input("目标涨跌幅 %", value=-10.0 if option_type_label == "PUT" else 10.0, step=1.0)

        c1, c2, c3, c4 = st.columns(4)
        take_profit_pct = c1.number_input("权利金止盈 %", min_value=1.0, value=80.0, step=5.0)
        stop_loss_pct = c2.number_input("权利金止损 %", min_value=1.0, max_value=99.0, value=40.0, step=5.0)
        time_stop_dte = c3.number_input("时间止损 DTE", min_value=1, value=14, step=1)
        max_hold_days = c4.number_input("最多持有天数", min_value=1, value=10, step=1)

        invalidation_default = spot * (1.04 if option_type_label == "PUT" else 0.96)
        invalidation_price = st.number_input("标的失效价", min_value=0.0, value=float(round(invalidation_default, 2)), step=0.5)

        c1, c2 = st.columns(2)
        strategy = c1.text_input("策略/计划", value="")
        thesis = c2.text_input("交易理由", value="")
        tags = st.text_input("标签", value="")
        submitted = st.form_submit_button("计算")

    if submitted:
        st.session_state["short_option_ready"] = True
    if not st.session_state.get("short_option_ready"):
        return

    option_type = option_type_label.lower()
    days = dte(expiry)
    greeks = black_scholes(spot, strike, days, rate, iv, option_type)
    theoretical = greeks.price
    overpay = (ask - theoretical) / theoretical * 100 if theoretical > 0 else 0.0
    t_pct = theta_pct(greeks.theta, ask)
    v_pct = vega_pct(greeks.vega, ask)
    scores = {
        "Delta": score_delta(abs(greeks.delta)),
        "Theta": score_theta_pct(t_pct),
        "Vega": score_vega_pct(v_pct),
        "DTE": score_dte(days),
        "IV Rank": score_iv_rank(iv_rank),
    }
    overall = aggregate_score(scores)
    target_spot = spot * (1 + target_move / 100)
    target_intrinsic = max(0.0, target_spot - strike) if option_type == "call" else max(0.0, strike - target_spot)
    target_pnl = target_intrinsic - ask
    cost = ask * int(contracts) * 100
    take_profit_premium = ask * (1 + take_profit_pct / 100)
    stop_loss_premium = ask * (1 - stop_loss_pct / 100)
    latest_time_exit = min(date.today() + timedelta(days=int(max_hold_days)), expiry - timedelta(days=int(time_stop_dte)))
    latest_time_exit = max(date.today(), latest_time_exit)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("综合判断", STATUS_LABEL[overall])
    c2.metric("BS 理论价", _money(theoretical), f"{overpay:+.1f}% vs Ask")
    c3.metric("盈亏平衡", _money(breakeven(strike, ask, option_type)))
    c4.metric("本笔成本", _money(cost))

    st.subheader("止盈止损计划")
    plan = _trade_plan_frame(
        spot=spot,
        strike=strike,
        ask=ask,
        days=days,
        rate=rate,
        iv=iv,
        option_type=option_type,
        take_profit_premium=take_profit_premium,
        stop_loss_premium=stop_loss_premium,
        invalidation_price=invalidation_price,
        latest_time_exit=latest_time_exit,
    )
    st.dataframe(plan, width="stretch", hide_index=True)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("止盈权利金", _money(take_profit_premium), f"+{take_profit_pct:.0f}%")
    c2.metric("止损权利金", _money(stop_loss_premium), f"-{stop_loss_pct:.0f}%")
    c3.metric("时间止损日", latest_time_exit.isoformat())
    c4.metric("标的失效价", _money(invalidation_price))

    st.dataframe(_score_frame(scores), width="stretch", hide_index=True)
    _render_greeks(greeks, ask)

    st.subheader("仓位建议")
    unit_cost = ask * 100
    sizing = pd.DataFrame(
        [
            {"规则": "单笔 1%", "张数": int(account_size * 0.01 // unit_cost), "金额": account_size * 0.01},
            {"规则": "单标的 3%", "张数": int(account_size * 0.03 // unit_cost), "金额": account_size * 0.03},
            {"规则": "期权总仓 10%", "张数": int(account_size * 0.10 // unit_cost), "金额": account_size * 0.10},
        ]
    )
    sizing["金额"] = sizing["金额"].map(_money)
    st.dataframe(sizing, width="stretch", hide_index=True)

    c1, c2, c3 = st.columns(3)
    c1.metric("目标标的价", _money(target_spot))
    c2.metric("目标到期内在价值", _money(target_intrinsic))
    c3.metric("目标到期收益", f"{target_pnl / ask * 100:+.0f}%")

    st.subheader("情景矩阵")
    matrix = pd.DataFrame(scenario_matrix(spot, strike, ask, days, rate, iv, option_type))
    st.dataframe(_format_scenario_matrix(matrix), width="stretch", hide_index=True)

    if st.button("保存为买入开仓记录", type="primary"):
        append_trade(
            {
                "trade_date": date.today().isoformat(),
                "ticker": ticker,
                "option_type": option_type,
                "expiry": expiry.isoformat(),
                "strike": strike,
                "action": "买入开仓",
                "contracts": int(contracts),
                "premium": ask,
                "spot": spot,
                "iv": iv,
                "fees": 0,
                "strategy": strategy,
                "thesis": _build_trade_plan_text(
                    thesis,
                    take_profit_premium,
                    stop_loss_premium,
                    invalidation_price,
                    latest_time_exit,
                    take_profit_pct,
                    stop_loss_pct,
                ),
                "tags": tags,
            }
        )
        st.success("已保存。")
        st.rerun()


def _short_option_page(account_snapshots: pd.DataFrame) -> None:
    st.subheader("卖出计划")
    account_default = _latest_account_size(account_snapshots)
    latest = _latest_account_snapshot(account_snapshots)
    latest_account = str(latest["account"]) if latest is not None and str(latest["account"]).strip() else "主账户"
    latest_net_liq = float(latest["net_liq"]) if latest is not None else account_default
    latest_cash = float(latest["cash"]) if latest is not None else 0.0
    latest_buying_power = float(latest["buying_power"]) if latest is not None else account_default
    latest_margin_used = float(latest["margin_used"]) if latest is not None else 0.0

    with st.form("short_option_form"):
        c1, c2, c3, c4 = st.columns(4)
        ticker = c1.text_input("标的", value="PLTR", key="short_ticker").upper()
        option_type_label = c2.selectbox("类型", ["PUT", "CALL"], index=0, key="short_option_type")
        expiry = c3.date_input("到期日", value=date.today() + timedelta(days=45), key="short_expiry")
        account_size = c4.number_input("账户总额", min_value=0.0, value=float(account_default), step=1000.0, key="short_account_size")

        c1, c2, c3, c4 = st.columns(4)
        spot = c1.number_input("标的现价", min_value=0.01, value=142.0, step=0.01, key="short_spot")
        strike = c2.number_input("行权价", min_value=0.01, value=130.0, step=0.5, key="short_strike")
        bid = c3.number_input("Bid/卖出权利金", min_value=0.01, value=3.0, step=0.01, key="short_bid")
        contracts = c4.number_input("计划张数", min_value=1, value=1, step=1, key="short_contracts")

        c1, c2, c3, c4 = st.columns(4)
        iv = c1.number_input("IV %", min_value=0.1, value=55.0, step=0.1, key="short_iv")
        rate = c2.number_input("无风险利率 %", value=4.3, step=0.01, key="short_rate")
        iv_rank = c3.slider("IV Rank", min_value=0, max_value=100, value=65, key="short_iv_rank")
        collateral_mode = c4.selectbox("担保方式", _short_collateral_modes(option_type_label), key="short_collateral_mode")

        c1, c2, c3, c4 = st.columns(4)
        take_profit_pct = c1.number_input("买回止盈 %", min_value=1.0, max_value=99.0, value=50.0, step=5.0, key="short_take_profit_pct")
        stop_loss_pct = c2.number_input("买回止损 %", min_value=1.0, value=100.0, step=10.0, key="short_stop_loss_pct")
        time_stop_dte = c3.number_input("时间止损 DTE", min_value=1, value=14, step=1, key="short_time_stop_dte")
        fees = c4.number_input("开仓手续费", min_value=0.0, value=0.0, step=0.1, key="short_fees")

        invalidation_default = spot * (0.96 if option_type_label == "PUT" else 1.04)
        invalidation_price = st.number_input("标的失效价", min_value=0.0, value=float(round(invalidation_default, 2)), step=0.5, key="short_invalidation")

        c1, c2, c3 = st.columns(3)
        sync_account = c1.checkbox("保存时同步账户资金", value=True, key="short_sync_account")
        account = c2.text_input("同步账户", value=latest_account, key="short_account")
        strategy = c3.text_input("策略/计划", value="卖方收租", key="short_strategy")
        thesis = st.text_input("交易理由", value="", key="short_thesis")
        tags = st.text_input("标签", value="", key="short_tags")
        submitted = st.form_submit_button("计算")

    if not submitted:
        return

    option_type = option_type_label.lower()
    qty = int(contracts)
    days = dte(expiry)
    greeks = black_scholes(spot, strike, days, rate, iv, option_type)
    theoretical = greeks.price
    edge = (bid - theoretical) / theoretical * 100 if theoretical > 0 else 0.0
    credit = bid * qty * 100 - fees
    buyback_target = bid * (1 - take_profit_pct / 100)
    stop_loss_premium = bid * (1 + stop_loss_pct / 100)
    max_profit = credit
    breakeven_price = breakeven(strike, bid, option_type)
    collateral = _short_collateral_estimate(spot, strike, bid, option_type, qty, collateral_mode)
    max_loss = _short_max_loss(strike, bid, option_type, qty, collateral_mode)
    annualized_yield = max_profit / collateral * (365 / max(days, 1)) * 100 if collateral else 0.0
    pop = max(0.0, min(100.0, (1 - abs(greeks.delta)) * 100))
    latest_time_exit = max(date.today(), min(date.today() + timedelta(days=max(days - int(time_stop_dte), 0)), expiry - timedelta(days=int(time_stop_dte))))

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("收取权利金", _money(credit))
    c2.metric("盈亏平衡", _money(breakeven_price))
    c3.metric("估算占用资金", _money(collateral))
    c4.metric("年化权利金", f"{annualized_yield:.1f}%")
    c5.metric("Delta 粗估胜率", f"{pop:.1f}%")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("BS 理论价", _money(theoretical), f"{edge:+.1f}% vs Bid")
    c2.metric("最大利润", _money(max_profit))
    c3.metric("最大亏损", _money(max_loss) if max_loss is not None else "理论无限")
    c4.metric("被行权价格", _assignment_label(strike, bid, option_type, collateral_mode))

    st.subheader("买回止盈止损计划")
    st.dataframe(
        _short_trade_plan_frame(
            spot=spot,
            strike=strike,
            days=days,
            rate=rate,
            iv=iv,
            option_type=option_type,
            buyback_target=buyback_target,
            stop_loss_premium=stop_loss_premium,
            invalidation_price=invalidation_price,
            latest_time_exit=latest_time_exit,
            breakeven_price=breakeven_price,
        ),
        width="stretch",
        hide_index=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("止盈买回价", _money(buyback_target), f"-{take_profit_pct:.0f}%")
    c2.metric("止损买回价", _money(stop_loss_premium), f"+{stop_loss_pct:.0f}%")
    c3.metric("时间止损日", latest_time_exit.isoformat())
    c4.metric("标的失效价", _money(invalidation_price))

    st.subheader("仓位约束")
    sizing = pd.DataFrame(
        [
            {"规则": "单笔占用 <= 5%", "最大张数": int(account_size * 0.05 // max(collateral / qty, 0.01)), "金额": account_size * 0.05},
            {"规则": "单标的占用 <= 10%", "最大张数": int(account_size * 0.10 // max(collateral / qty, 0.01)), "金额": account_size * 0.10},
            {"规则": "卖方总占用 <= 30%", "最大张数": int(account_size * 0.30 // max(collateral / qty, 0.01)), "金额": account_size * 0.30},
        ]
    )
    sizing["金额"] = sizing["金额"].map(_money)
    st.dataframe(sizing, width="stretch", hide_index=True)
    st.dataframe(_short_score_frame(abs(greeks.delta), days, iv_rank, max_profit / collateral * 100 if collateral else 0), width="stretch", hide_index=True)
    _render_short_greeks(greeks, bid)

    if sync_account:
        cash_after = latest_cash + credit
        buying_power_after = max(0.0, latest_buying_power + credit - collateral)
        margin_after = latest_margin_used + collateral
        st.subheader("账户资金同步预览")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("同步后净值", _money(latest_net_liq))
        c2.metric("同步后现金", _money(cash_after))
        c3.metric("同步后购买力", _money(buying_power_after))
        c4.metric("同步后占用资金", _money(margin_after))

    if st.button("保存为卖出开仓记录", type="primary"):
        append_trade(
            {
                "trade_date": date.today().isoformat(),
                "ticker": ticker,
                "option_type": option_type,
                "expiry": expiry.isoformat(),
                "strike": strike,
                "action": "卖出开仓",
                "contracts": qty,
                "premium": bid,
                "spot": spot,
                "iv": iv,
                "fees": fees,
                "strategy": strategy,
                "thesis": _build_short_trade_plan_text(
                    thesis,
                    buyback_target,
                    stop_loss_premium,
                    invalidation_price,
                    latest_time_exit,
                    take_profit_pct,
                    stop_loss_pct,
                    collateral_mode,
                    collateral,
                ),
                "tags": tags,
            }
        )
        if sync_account:
            append_account_snapshot(
                {
                    "record_date": date.today().isoformat(),
                    "account": account,
                    "net_liq": latest_net_liq,
                    "cash": cash_after,
                    "buying_power": buying_power_after,
                    "margin_used": margin_after,
                    "deposit": 0,
                    "withdrawal": 0,
                    "realized_pnl": 0,
                    "notes": f"{ticker} {expiry.isoformat()} {strike:.2f} {option_type.upper()} 卖出开仓 {qty} 张，收权利金 {_money(credit)}，占用资金估算 {_money(collateral)}",
                }
            )
        st.success("已保存。")
        st.rerun()


def _sell_page(positions: pd.DataFrame) -> None:
    st.subheader("卖出/平仓计算")
    selected_position = None
    if not positions.empty:
        labels = ["手动输入"] + positions["contract_key"].tolist()
        selected = st.selectbox("选择持仓", labels)
        if selected != "手动输入":
            selected_position = positions[positions["contract_key"] == selected].iloc[0]
    else:
        st.info("暂无持仓，可手动输入。")

    default_type = str(selected_position["option_type"]).upper() if selected_position is not None else "PUT"
    default_expiry = pd.to_datetime(selected_position["expiry"]).date() if selected_position is not None else date.today() + timedelta(days=30)
    default_strike = float(selected_position["strike"]) if selected_position is not None else 150.0
    default_cost = float(selected_position["avg_price"]) if selected_position is not None else 7.1
    default_contracts = int(selected_position["contracts"]) if selected_position is not None else 1
    default_ticker = str(selected_position["ticker"]) if selected_position is not None else "PLTR"
    default_direction = str(selected_position["direction"]) if selected_position is not None else "long"

    with st.form("sell_calc_form"):
        c1, c2, c3, c4 = st.columns(4)
        ticker = c1.text_input("标的", value=default_ticker).upper()
        option_type_label = c2.selectbox("类型", ["PUT", "CALL"], index=0 if default_type == "PUT" else 1)
        expiry = c3.date_input("到期日", value=default_expiry)
        direction = c4.selectbox("持仓方向", ["long", "short"], index=0 if default_direction == "long" else 1)

        c1, c2, c3, c4 = st.columns(4)
        strike = c1.number_input("行权价", min_value=0.01, value=default_strike, step=0.5)
        avg_cost = c2.number_input("持仓均价/信用", min_value=0.01, value=default_cost, step=0.01)
        current_premium = c3.number_input("当前权利金", min_value=0.01, value=round(default_cost * 1.3, 2), step=0.01)
        close_contracts = c4.number_input("平仓张数", min_value=1, value=default_contracts, step=1)

        c1, c2, c3 = st.columns(3)
        spot = c1.number_input("当前标的价", min_value=0.01, value=float(selected_position["last_spot"]) if selected_position is not None and selected_position["last_spot"] else 142.0, step=0.01)
        iv = c2.number_input("当前 IV %", min_value=0.1, value=float(selected_position["last_iv"]) if selected_position is not None and selected_position["last_iv"] else 50.0, step=0.1)
        fees = c3.number_input("手续费", min_value=0.0, value=0.0, step=0.1)
        submitted = st.form_submit_button("计算")

    if not submitted:
        return

    option_type = option_type_label.lower()
    days = dte(expiry)
    greeks = black_scholes(spot, strike, days, 4.3, iv, option_type)
    if direction == "long":
        realized = (current_premium - avg_cost) * int(close_contracts) * 100 - fees
        gain_pct = (current_premium - avg_cost) / avg_cost * 100
        action = "卖出平仓"
    else:
        realized = (avg_cost - current_premium) * int(close_contracts) * 100 - fees
        gain_pct = (avg_cost - current_premium) / avg_cost * 100
        action = "买入平仓"

    match_price = breakeven(strike, current_premium, option_type)
    entry_break = breakeven(strike, avg_cost, option_type)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("平仓盈亏", _money(realized), f"{gain_pct:+.1f}%")
    c2.metric("当前权利金", _money(current_premium))
    c3.metric("持有到期需达到", _money(match_price))
    c4.metric("入场盈亏平衡", _money(entry_break))

    _render_greeks(greeks, current_premium)
    advice = _exit_advice(gain_pct, days, greeks, current_premium)
    st.dataframe(pd.DataFrame({"出场信号": advice}), width="stretch", hide_index=True)

    if st.button(f"保存为{action}记录", type="primary"):
        append_trade(
            {
                "trade_date": date.today().isoformat(),
                "ticker": ticker,
                "option_type": option_type,
                "expiry": expiry.isoformat(),
                "strike": strike,
                "action": action,
                "contracts": int(close_contracts),
                "premium": current_premium,
                "spot": spot,
                "iv": iv,
                "fees": fees,
                "strategy": "",
                "thesis": "",
                "tags": "",
            }
        )
        st.success("已保存。")
        st.rerun()


def _strategy_page() -> None:
    st.subheader("策略组合")
    c1, c2, c3, c4 = st.columns(4)
    spot = c1.number_input("现价", min_value=0.01, value=142.0, step=0.01, key="strategy_spot")
    expiry = c2.date_input("到期日", value=date.today() + timedelta(days=45), key="strategy_expiry")
    iv = c3.number_input("IV %", min_value=0.1, value=55.0, step=0.1, key="strategy_iv")
    rate = c4.number_input("利率 %", value=4.3, step=0.01, key="strategy_rate")

    leg_count = st.number_input("腿数", min_value=1, max_value=4, value=2, step=1)
    defaults = [
        ("buy", "call", spot, 1),
        ("sell", "call", spot * 1.05, 1),
        ("buy", "put", spot * 0.95, 1),
        ("sell", "put", spot * 0.90, 1),
    ]
    legs: list[OptionLeg] = []
    rows = []
    for index in range(int(leg_count)):
        d_action, d_type, d_strike, d_qty = defaults[index]
        c1, c2, c3, c4, c5 = st.columns(5)
        action = c1.selectbox("买/卖", ["buy", "sell"], index=0 if d_action == "buy" else 1, key=f"leg_action_{index}")
        option_type = c2.selectbox("类型", ["call", "put"], index=0 if d_type == "call" else 1, key=f"leg_type_{index}")
        strike = c3.number_input("行权价", min_value=0.01, value=float(round(d_strike, 2)), step=0.5, key=f"leg_strike_{index}")
        qty = c4.number_input("张数", min_value=1, value=d_qty, step=1, key=f"leg_qty_{index}")
        default_premium = black_scholes(spot, strike, dte(expiry), rate, iv, option_type).price
        premium = c5.number_input("权利金", min_value=0.0, value=float(round(default_premium, 2)), step=0.01, key=f"leg_premium_{index}")
        legs.append(OptionLeg(action=action, option_type=option_type, strike=strike, contracts=int(qty), premium=premium))
        greek = black_scholes(spot, strike, dte(expiry), rate, iv, option_type)
        sign = 1 if action == "buy" else -1
        rows.append(
            {
                "腿": index + 1,
                "方向": action,
                "类型": option_type,
                "行权价": strike,
                "张数": int(qty),
                "权利金": premium,
                "Delta": greek.delta * sign * int(qty),
                "Theta": greek.theta * sign * int(qty),
                "Vega": greek.vega * sign * int(qty),
            }
        )

    metrics = strategy_metrics(spot, legs)
    legs_df = pd.DataFrame(rows)
    st.dataframe(legs_df, width="stretch", hide_index=True)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("净借记/信用", _money(float(metrics["net_debit"]) * 100))
    c2.metric("扫描最大利润", _money(float(metrics["max_profit"]) * 100))
    c3.metric("扫描最大亏损", _money(float(metrics["max_loss"]) * 100))
    c4.metric("盈亏平衡", " / ".join(_money(value) for value in metrics["breakevens"][:4]) or "无")
    curve = pd.DataFrame(metrics["curve"])
    fig = px.line(curve, x="标的价格", y="每组合盈亏")
    fig.add_hline(y=0, line_dash="dash", line_color="#888")
    st.plotly_chart(fig, width="stretch")


def _trades_page(trades: pd.DataFrame, realized: pd.DataFrame) -> None:
    st.subheader("交易记录")
    with st.expander("新增手动记录", expanded=False):
        with st.form("manual_trade"):
            c1, c2, c3, c4 = st.columns(4)
            trade_date = c1.date_input("交易日", value=date.today())
            ticker = c2.text_input("标的", value="PLTR").upper()
            option_type = c3.selectbox("类型", ["put", "call"])
            expiry = c4.date_input("到期日", value=date.today() + timedelta(days=30))
            c1, c2, c3, c4 = st.columns(4)
            strike = c1.number_input("行权价", min_value=0.01, value=140.0, step=0.5)
            action = c2.selectbox("动作", ["买入开仓", "卖出平仓", "卖出开仓", "买入平仓"])
            contracts = c3.number_input("张数", min_value=1, value=1, step=1)
            premium = c4.number_input("权利金", min_value=0.0, value=1.0, step=0.01)
            c1, c2, c3 = st.columns(3)
            spot = c1.number_input("标的价", min_value=0.0, value=0.0, step=0.01)
            iv = c2.number_input("IV %", min_value=0.0, value=0.0, step=0.1)
            fees = c3.number_input("手续费", min_value=0.0, value=0.0, step=0.1)
            strategy = st.text_input("策略")
            thesis = st.text_input("理由")
            tags = st.text_input("标签")
            if st.form_submit_button("保存记录", type="primary"):
                append_trade(
                    {
                        "trade_date": trade_date.isoformat(),
                        "ticker": ticker,
                        "option_type": option_type,
                        "expiry": expiry.isoformat(),
                        "strike": strike,
                        "action": action,
                        "contracts": int(contracts),
                        "premium": premium,
                        "spot": spot,
                        "iv": iv,
                        "fees": fees,
                        "strategy": strategy,
                        "thesis": thesis,
                        "tags": tags,
                    }
                )
                st.success("已保存。")
                st.rerun()

    if trades.empty:
        st.info("暂无交易记录。")
        return

    st.dataframe(trades.sort_values("trade_date", ascending=False), width="stretch", hide_index=True)
    c1, c2 = st.columns(2)
    c1.download_button("导出交易 CSV", data=trades.to_csv(index=False).encode("utf-8"), file_name="options_trades.csv")
    delete_id = c2.selectbox("删除记录 ID", [""] + trades["id"].tolist())
    if delete_id and st.button("删除所选记录"):
        save_trades(trades[trades["id"] != delete_id])
        st.success("已删除。")
        st.rerun()

    if not realized.empty:
        st.subheader("已实现盈亏")
        st.dataframe(realized, width="stretch", hide_index=True)


def _review_page(positions: pd.DataFrame, realized: pd.DataFrame, trades: pd.DataFrame) -> None:
    st.subheader("复盘看板")
    reviews = load_reviews()
    _performance_dashboard(realized, reviews, trades)

    st.subheader("新增复盘")
    contract_options = sorted(set(positions.get("contract_key", pd.Series(dtype=str)).tolist() + realized.get("contract_key", pd.Series(dtype=str)).tolist()))
    with st.form("review_form"):
        c1, c2, c3 = st.columns(3)
        review_date = c1.date_input("复盘日期", value=date.today())
        ticker = c2.text_input("标的", value="")
        contract = c3.selectbox("合约", [""] + contract_options)
        c1, c2, c3, c4 = st.columns(4)
        pnl = c1.number_input("盈亏金额", value=0.0, step=10.0)
        pnl_pct = c2.number_input("盈亏百分比", value=0.0, step=1.0)
        emotion = c3.slider("情绪控制", 1, 5, 3)
        execution = c4.slider("执行质量", 1, 5, 3)
        setup = st.text_input("交易形态/策略")
        entry_reason = st.text_area("入场理由", height=80)
        exit_reason = st.text_area("出场理由", height=80)
        rule_followed = st.selectbox("是否按计划执行", ["是", "部分", "否"])
        mistake_tags = st.text_input("问题标签")
        lessons = st.text_area("经验教训", height=100)
        next_action = st.text_area("下次动作", height=80)
        if st.form_submit_button("保存复盘", type="primary"):
            append_review(
                {
                    "review_date": review_date.isoformat(),
                    "ticker": ticker.upper(),
                    "contract_key": contract,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "setup": setup,
                    "entry_reason": entry_reason,
                    "exit_reason": exit_reason,
                    "rule_followed": rule_followed,
                    "emotion_score": emotion,
                    "execution_score": execution,
                    "mistake_tags": mistake_tags,
                    "lessons": lessons,
                    "next_action": next_action,
                }
            )
            st.success("已保存。")
            st.rerun()

    st.subheader("复盘记录")
    if reviews.empty:
        st.info("暂无复盘记录。")
        return

    st.dataframe(reviews.sort_values("review_date", ascending=False), width="stretch", hide_index=True)
    st.download_button("导出复盘 CSV", data=reviews.to_csv(index=False).encode("utf-8"), file_name="options_reviews.csv")
    delete_id = st.selectbox("删除复盘 ID", [""] + reviews["id"].tolist())
    if delete_id and st.button("删除所选复盘"):
        save_reviews(reviews[reviews["id"] != delete_id])
        st.success("已删除。")
        st.rerun()


def _trade_plan_frame(
    spot: float,
    strike: float,
    ask: float,
    days: int,
    rate: float,
    iv: float,
    option_type: str,
    take_profit_premium: float,
    stop_loss_premium: float,
    invalidation_price: float,
    latest_time_exit: date,
) -> pd.DataFrame:
    checkpoints = [days, max(1, round(days * 0.66)), max(1, round(days * 0.33)), max(1, min(days, 14))]
    seen: set[int] = set()
    rows: list[dict[str, object]] = []
    for remaining_days in checkpoints:
        if remaining_days in seen:
            continue
        seen.add(remaining_days)
        tp_spot = required_spot_for_premium(take_profit_premium, spot, strike, remaining_days, rate, iv, option_type)
        sl_spot = required_spot_for_premium(stop_loss_premium, spot, strike, remaining_days, rate, iv, option_type)
        rows.append(
            {
                "剩余时间": f"{remaining_days} 天",
                "止盈所需标的价": _spot_label(tp_spot, spot),
                "止损对应标的价": _spot_label(sl_spot, spot),
                "止盈权利金": _money(take_profit_premium),
                "止损权利金": _money(stop_loss_premium),
            }
        )
    rows.append(
        {
            "剩余时间": "纪律规则",
            "止盈所需标的价": "达到止盈权利金先减仓/平仓",
            "止损对应标的价": f"跌破/突破失效价 {_money(invalidation_price)}",
            "止盈权利金": f"时间止损日 {latest_time_exit.isoformat()}",
            "止损权利金": "到时不因希望而续命",
        }
    )
    return pd.DataFrame(rows)


def _build_trade_plan_text(
    thesis: str,
    take_profit_premium: float,
    stop_loss_premium: float,
    invalidation_price: float,
    latest_time_exit: date,
    take_profit_pct: float,
    stop_loss_pct: float,
) -> str:
    plan = (
        f"计划: 权利金止盈 {_money(take_profit_premium)} (+{take_profit_pct:.0f}%), "
        f"权利金止损 {_money(stop_loss_premium)} (-{stop_loss_pct:.0f}%), "
        f"标的失效价 {_money(invalidation_price)}, 时间止损 {latest_time_exit.isoformat()}。"
    )
    return f"{thesis}\n{plan}".strip()


def _short_collateral_modes(option_type_label: str) -> list[str]:
    if option_type_label == "PUT":
        return ["现金担保 PUT", "裸卖/券商保证金"]
    return ["备兑 CALL", "裸卖/券商保证金"]


def _short_collateral_estimate(
    spot: float,
    strike: float,
    premium: float,
    option_type: str,
    contracts: int,
    collateral_mode: str,
) -> float:
    qty = int(contracts)
    if collateral_mode == "现金担保 PUT":
        return strike * qty * 100
    if collateral_mode == "备兑 CALL":
        return spot * qty * 100

    otm = max(strike - spot, 0.0) if option_type == "call" else max(spot - strike, 0.0)
    per_share_margin = max(spot * 0.20 - otm + premium, spot * 0.10 + premium, premium)
    return max(per_share_margin, 0.0) * qty * 100


def _short_max_loss(strike: float, premium: float, option_type: str, contracts: int, collateral_mode: str) -> float | None:
    qty = int(contracts)
    if option_type == "put":
        return max(strike - premium, 0.0) * qty * 100
    if collateral_mode == "备兑 CALL":
        return None
    return None


def _assignment_label(strike: float, premium: float, option_type: str, collateral_mode: str) -> str:
    if option_type == "put":
        return f"接股成本 {_money(strike - premium)}"
    if collateral_mode == "备兑 CALL":
        return f"出让价 {_money(strike + premium)}"
    return "理论无限风险"


def _short_trade_plan_frame(
    spot: float,
    strike: float,
    days: int,
    rate: float,
    iv: float,
    option_type: str,
    buyback_target: float,
    stop_loss_premium: float,
    invalidation_price: float,
    latest_time_exit: date,
    breakeven_price: float,
) -> pd.DataFrame:
    checkpoints = [days, max(1, round(days * 0.66)), max(1, round(days * 0.33)), max(1, min(days, 14))]
    seen: set[int] = set()
    rows: list[dict[str, object]] = []
    for remaining_days in checkpoints:
        if remaining_days in seen:
            continue
        seen.add(remaining_days)
        tp_spot = required_spot_for_premium(buyback_target, spot, strike, remaining_days, rate, iv, option_type)
        sl_spot = required_spot_for_premium(stop_loss_premium, spot, strike, remaining_days, rate, iv, option_type)
        rows.append(
            {
                "剩余时间": f"{remaining_days} 天",
                "止盈买回对应标的": _spot_label(tp_spot, spot),
                "止损买回对应标的": _spot_label(sl_spot, spot),
                "止盈买回价": _money(buyback_target),
                "止损买回价": _money(stop_loss_premium),
            }
        )
    rows.append(
        {
            "剩余时间": "纪律规则",
            "止盈买回对应标的": "权利金回落到目标价可买回",
            "止损买回对应标的": f"失效价 {_money(invalidation_price)} / 盈亏平衡 {_money(breakeven_price)}",
            "止盈买回价": f"时间止损日 {latest_time_exit.isoformat()}",
            "止损买回价": "卖方不要把小亏拖成尾部风险",
        }
    )
    return pd.DataFrame(rows)


def _short_score_frame(abs_delta: float, days: int, iv_rank: int, yield_on_collateral: float) -> pd.DataFrame:
    scores = {
        "Delta 风险": "green" if abs_delta <= 0.30 else "yellow" if abs_delta <= 0.50 else "red",
        "DTE": "green" if 21 <= days <= 60 else "yellow" if 7 <= days <= 75 else "red",
        "IV Rank": "green" if iv_rank >= 50 else "yellow" if iv_rank >= 30 else "red",
        "权利金/占用": "green" if yield_on_collateral >= 1.0 else "yellow" if yield_on_collateral >= 0.5 else "red",
    }
    return pd.DataFrame(
        {
            "维度": list(scores.keys()),
            "状态": [STATUS_LABEL[value] for value in scores.values()],
            "颜色": list(scores.values()),
        }
    )


def _render_short_greeks(greeks, premium: float) -> None:
    data = pd.DataFrame(
        [
            {"指标": "Short Delta", "值": -greeks.delta, "说明": "卖方方向暴露"},
            {"指标": "Short Gamma", "值": -greeks.gamma, "说明": "不利加速度"},
            {"指标": "Short Theta/天", "值": -greeks.theta, "说明": f"{theta_pct(greeks.theta, premium):.2f}%/天"},
            {"指标": "Short Vega", "值": -greeks.vega, "说明": f"{vega_pct(greeks.vega, premium):.2f}%/1% IV"},
            {"指标": "Short Rho", "值": -greeks.rho, "说明": "利率敏感度"},
        ]
    )
    st.dataframe(data, width="stretch", hide_index=True)


def _build_short_trade_plan_text(
    thesis: str,
    buyback_target: float,
    stop_loss_premium: float,
    invalidation_price: float,
    latest_time_exit: date,
    take_profit_pct: float,
    stop_loss_pct: float,
    collateral_mode: str,
    collateral: float,
) -> str:
    plan = (
        f"计划: 买回止盈 {_money(buyback_target)} (-{take_profit_pct:.0f}%), "
        f"买回止损 {_money(stop_loss_premium)} (+{stop_loss_pct:.0f}%), "
        f"标的失效价 {_money(invalidation_price)}, 时间止损 {latest_time_exit.isoformat()}, "
        f"{collateral_mode} 占用估算 {_money(collateral)}。"
    )
    return f"{thesis}\n{plan}".strip()


def _performance_dashboard(realized: pd.DataFrame, reviews: pd.DataFrame, trades: pd.DataFrame) -> None:
    closed = realized.copy()
    if closed.empty:
        win_rate = 0.0
        total_pnl = 0.0
        avg_win = 0.0
        avg_loss = 0.0
        profit_factor = 0.0
    else:
        wins = closed[closed["realized_pnl"] > 0]
        losses = closed[closed["realized_pnl"] < 0]
        win_rate = len(wins) / len(closed) * 100
        total_pnl = float(closed["realized_pnl"].sum())
        avg_win = float(wins["realized_pnl"].mean()) if not wins.empty else 0.0
        avg_loss = float(losses["realized_pnl"].mean()) if not losses.empty else 0.0
        gross_win = float(wins["realized_pnl"].sum()) if not wins.empty else 0.0
        gross_loss = abs(float(losses["realized_pnl"].sum())) if not losses.empty else 0.0
        profit_factor = gross_win / gross_loss if gross_loss else 0.0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("已平仓笔数", len(closed))
    c2.metric("胜率", f"{win_rate:.1f}%")
    c3.metric("已实现盈亏", _money(total_pnl))
    c4.metric("平均赢/亏", f"{_money(avg_win)} / {_money(avg_loss)}")
    c5.metric("Profit Factor", f"{profit_factor:.2f}" if profit_factor else "暂无")

    if not closed.empty:
        st.subheader("盈亏分布")
        chart_df = closed.copy()
        chart_df["结果"] = chart_df["realized_pnl"].apply(lambda value: "盈利" if value > 0 else "亏损" if value < 0 else "打平")
        st.plotly_chart(px.bar(chart_df, x="trade_date", y="realized_pnl", color="结果", hover_data=["contract_key"]), width="stretch")

        by_ticker = chart_df.groupby("ticker", as_index=False)["realized_pnl"].sum().sort_values("realized_pnl", ascending=False)
        st.plotly_chart(px.bar(by_ticker, x="ticker", y="realized_pnl"), width="stretch")

    if not reviews.empty:
        st.subheader("复盘问题聚类")
        c1, c2, c3 = st.columns(3)
        c1.metric("复盘数", len(reviews))
        c2.metric("平均执行", f"{float(reviews['execution_score'].mean()):.1f}/5")
        c3.metric("平均情绪", f"{float(reviews['emotion_score'].mean()):.1f}/5")

        tag_counts = _split_tag_counts(reviews["mistake_tags"].tolist())
        if not tag_counts.empty:
            st.plotly_chart(px.bar(tag_counts, x="标签", y="次数"), width="stretch")

        rule_counts = reviews.groupby("rule_followed", as_index=False).size().rename(columns={"size": "次数", "rule_followed": "是否按计划"})
        st.plotly_chart(px.bar(rule_counts, x="是否按计划", y="次数"), width="stretch")

        setup_pnl = reviews.groupby("setup", as_index=False)["pnl"].sum().sort_values("pnl", ascending=False)
        setup_pnl = setup_pnl[setup_pnl["setup"].astype(str).str.len() > 0]
        if not setup_pnl.empty:
            st.plotly_chart(px.bar(setup_pnl, x="setup", y="pnl"), width="stretch")
    elif trades.empty:
        st.info("还没有交易和复盘数据。先记录几笔交易，平仓后这里会自动生成胜率和问题看板。")


def _split_tag_counts(values: list[object]) -> pd.DataFrame:
    counts: dict[str, int] = {}
    for value in values:
        for tag in str(value).replace("，", ",").replace("、", ",").split(","):
            cleaned = tag.strip()
            if not cleaned:
                continue
            counts[cleaned] = counts.get(cleaned, 0) + 1
    return pd.DataFrame({"标签": list(counts.keys()), "次数": list(counts.values())}).sort_values("次数", ascending=False)


def _latest_account_snapshot(account_snapshots: pd.DataFrame) -> pd.Series | None:
    if account_snapshots.empty:
        return None
    output = account_snapshots.copy()
    output["record_date_dt"] = pd.to_datetime(output["record_date"], errors="coerce")
    output = output.sort_values(["record_date_dt", "created_at"], na_position="first")
    return output.iloc[-1]


def _latest_account_size(account_snapshots: pd.DataFrame) -> float:
    latest = _latest_account_snapshot(account_snapshots)
    if latest is None:
        return 50000.0
    net_liq = float(latest["net_liq"])
    return net_liq if net_liq > 0 else 50000.0


def _render_greeks(greeks, premium: float) -> None:
    data = pd.DataFrame(
        [
            {"指标": "Delta", "值": greeks.delta, "说明": "方向暴露"},
            {"指标": "Gamma", "值": greeks.gamma, "说明": "Delta 加速度"},
            {"指标": "Theta/天", "值": greeks.theta, "说明": f"{theta_pct(greeks.theta, premium):.2f}%/天"},
            {"指标": "Vega", "值": greeks.vega, "说明": f"{vega_pct(greeks.vega, premium):.2f}%/1% IV"},
            {"指标": "Rho", "值": greeks.rho, "说明": "利率敏感度"},
        ]
    )
    st.dataframe(data, width="stretch", hide_index=True)


def _score_frame(scores: dict[str, str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "维度": list(scores.keys()),
            "状态": [STATUS_LABEL[value] for value in scores.values()],
            "颜色": [value for value in scores.values()],
        }
    )


def _exit_advice(gain_pct: float, days: int, greeks, premium: float) -> list[str]:
    advice: list[str] = []
    t_pct = theta_pct(greeks.theta, premium)
    if gain_pct >= 50:
        advice.append("浮盈 50% 以上，优先考虑至少减半锁利。")
    if gain_pct <= -50:
        advice.append("亏损 50% 以上，检查原始交易假设是否失效。")
    if t_pct > 3:
        advice.append(f"Theta 已到 {t_pct:.1f}%/天，时间衰减对买方很不友好。")
    if days <= 7:
        advice.append("剩余 7 天内，Gamma 风险和时间衰减都很高。")
    elif days <= 14:
        advice.append("剩余 14 天内，进入临期管理区。")
    if abs(greeks.delta) < 0.15:
        advice.append("Delta 很小，继续持有对方向变化不敏感。")
    if abs(greeks.delta) > 0.85:
        advice.append("Delta 接近 1，利润更多来自内在价值，可考虑锁利或换仓。")
    return advice or ["当前指标没有明显强制平仓信号，按原计划管理止盈止损。"]


def _format_scenario_matrix(df: pd.DataFrame) -> pd.DataFrame:
    output = df.copy()
    for column in output.columns:
        if "价格" in column or "理论价" in column:
            output[column] = output[column].map(lambda value: _money(float(value)))
        elif "盈亏%" in column or column == "涨跌幅":
            output[column] = output[column].map(lambda value: f"{float(value):+.0f}%")
    return output


def _spot_label(value: float | None, current_spot: float) -> str:
    if value is None:
        return "超出模型扫描范围"
    move = (value - current_spot) / current_spot * 100 if current_spot else 0.0
    return f"{_money(value)} ({move:+.1f}%)"


def _money(value: float) -> str:
    return f"${value:,.2f}"


def _style() -> None:
    st.markdown(
        """
<style>
div[data-testid="stMetric"] {
  background: #f7f8fa;
  border: 1px solid #e1e5ea;
  padding: 12px 14px;
  border-radius: 8px;
}
.stTabs [data-baseweb="tab-list"] {
  gap: 2px;
}
.stTabs [data-baseweb="tab"] {
  height: 40px;
}
</style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
