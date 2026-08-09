"use client";

import {
  BookMarked,
  BookOpen,
  CircleDollarSign,
  Download,
  LayoutDashboard,
  Loader2,
  Plus,
  RefreshCw,
  ReceiptText,
  Save,
  Settings,
  Trash2,
  TrendingDown,
  TrendingUp,
  Wallet
} from "lucide-react";
import type { FormEvent, InputHTMLAttributes, ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import type { PortfolioSnapshot } from "@/domain/portfolio";
import { formatMoney, formatNumber, formatPercent } from "@/domain/money";

type Tab = "overview" | "trades" | "journal" | "data";
type SubmitHandler = (
  event: FormEvent<HTMLFormElement>,
  endpoint: string,
  method?: string,
  reset?: boolean
) => void | Promise<void>;

const cashFlowLabels: Record<string, string> = {
  DEPOSIT: "转入",
  WITHDRAWAL: "转出",
  DIVIDEND: "分红",
  INTEREST: "利息",
  FEE: "费用",
  TAX: "税费",
  ADJUSTMENT: "调整"
};

const instrumentLabels: Record<string, string> = {
  stock: "股票",
  etf: "ETF",
  option: "期权",
  crypto: "Crypto",
  fund: "基金",
  other: "其他"
};

const directionLabels: Record<string, string> = {
  LONG: "做多",
  SHORT: "做空",
  WATCH: "观察"
};

const resultLabels: Record<string, string> = {
  OPEN: "进行中",
  WIN: "盈利",
  LOSS: "亏损",
  BREAKEVEN: "打平",
  MISSED: "错过"
};

const marketRegimeLabels: Record<string, string> = {
  uptrend: "上升趋势",
  downtrend: "下降趋势",
  range: "震荡",
  high_vol: "高波动",
  low_vol: "低波动",
  event: "事件驱动"
};

const navItems: Array<{ value: Tab; label: string; icon: ReactNode }> = [
  { value: "overview", label: "总览", icon: <LayoutDashboard size={16} /> },
  { value: "trades", label: "交易", icon: <ReceiptText size={16} /> },
  { value: "journal", label: "日志", icon: <BookMarked size={16} /> },
  { value: "data", label: "账户", icon: <Settings size={16} /> }
];

function today() {
  return new Date().toISOString().slice(0, 10);
}

function readForm(form: HTMLFormElement) {
  const out: Record<string, string | string[]> = {};
  for (const [key, value] of new FormData(form).entries()) {
    if (typeof value !== "string") continue;
    const current = out[key];
    if (current === undefined) {
      out[key] = value;
    } else if (Array.isArray(current)) {
      current.push(value);
    } else {
      out[key] = [current, value];
    }
  }
  return out;
}

function signedClass(value: number) {
  if (value > 0) return "positive";
  if (value < 0) return "negative";
  return "";
}

export function TradingWorkspace() {
  const [snapshot, setSnapshot] = useState<PortfolioSnapshot | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setError(null);
    const response = await fetch("/api/snapshot", { cache: "no-store" });
    if (!response.ok) throw new Error("snapshot failed");
    setSnapshot(await response.json());
  }

  async function submitForm(
    event: FormEvent<HTMLFormElement>,
    endpoint: string,
    method = "POST",
    reset = true
  ) {
    event.preventDefault();
    const form = event.currentTarget;
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(endpoint, {
        method,
        headers: { "content-type": "application/json" },
        body: JSON.stringify(readForm(form))
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.error || "保存失败");
      }
      if (reset) form.reset();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "操作失败");
    } finally {
      setBusy(false);
    }
  }

  async function remove(endpoint: string) {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(endpoint, { method: "DELETE" });
      if (!response.ok) throw new Error("删除失败");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    refresh().catch(() => setError("加载失败"));
  }, []);

  const currency = snapshot?.account.currency ?? "USD";
  const totals = snapshot?.totals;
  const topPositions = useMemo(() => snapshot?.positions.slice(0, 6) ?? [], [snapshot]);

  return (
    <main className="shell">
      <header className="topbar">
        <div className="topbar-title">
          <p className="eyebrow">Trading Journal</p>
          <h1>交易工作台</h1>
        </div>
        <div className="topbar-actions">
          {snapshot ? (
            <div className="account-chip">
              <span>{snapshot.account.name}</span>
              <strong>{snapshot.account.currency}</strong>
            </div>
          ) : null}
          <button className="icon-button ghost" type="button" onClick={() => refresh()} aria-label="刷新">
            <RefreshCw size={18} />
          </button>
          <a className="button secondary" href="/api/export">
            <Download size={17} />
            导出
          </a>
        </div>
      </header>

      {error ? <div className="alert">{error}</div> : null}

      {!snapshot ? (
        <div className="loading">
          <Loader2 className="spin" size={24} />
          加载中
        </div>
      ) : (
        <>
          <nav className="tabs" aria-label="交易工作台">
            {navItems.map((item) => (
              <button
                className={activeTab === item.value ? "tab active" : "tab"}
                type="button"
                key={item.value}
                onClick={() => setActiveTab(item.value)}
              >
                {item.icon}
                {item.label}
              </button>
            ))}
          </nav>

          {activeTab === "overview" ? (
            <section className="stack">
              <div className="metric-grid">
                <Metric
                  icon={<Wallet size={18} />}
                  label="总权益"
                  value={formatMoney(totals?.equityCents ?? 0, currency)}
                />
                <Metric
                  icon={<CircleDollarSign size={18} />}
                  label="现金"
                  value={formatMoney(totals?.cashCents ?? 0, currency)}
                />
                <Metric
                  icon={<TrendingUp size={18} />}
                  label="持仓市值"
                  value={formatMoney(totals?.positionValueCents ?? 0, currency)}
                  detail={formatPercent(totals?.exposurePct ?? 0)}
                />
                <Metric
                  icon={<TrendingDown size={18} />}
                  label="总盈亏"
                  value={formatMoney(totals?.totalPnlCents ?? 0, currency)}
                  tone={signedClass(totals?.totalPnlCents ?? 0)}
                />
              </div>

              <div className="work-grid">
                <section className="panel wide">
                  <div className="section-title">
                    <h2>持仓</h2>
                    <span>{snapshot.positions.length}</span>
                  </div>
                  <PositionsTable snapshot={snapshot} />
                </section>

                <section className="panel">
                  <div className="section-title">
                    <h2>统计</h2>
                  </div>
                  <div className="stat-list">
                    <StatRow label="已实现盈亏" value={formatMoney(snapshot.totals.realizedPnlCents, currency)} />
                    <StatRow label="浮动盈亏" value={formatMoney(snapshot.totals.unrealizedPnlCents, currency)} />
                    <StatRow label="胜率" value={formatPercent(snapshot.totals.winRate)} />
                    <StatRow
                      label="Profit Factor"
                      value={
                        snapshot.totals.profitFactor === null
                          ? "∞"
                          : formatNumber(snapshot.totals.profitFactor ?? 0, 2)
                      }
                    />
                    <StatRow label="平均盈利" value={formatMoney(snapshot.totals.avgWinCents, currency)} />
                    <StatRow label="平均亏损" value={formatMoney(snapshot.totals.avgLossCents, currency)} />
                    <StatRow label="最大单笔亏损" value={formatMoney(snapshot.totals.largestLossCents, currency)} />
                    <StatRow label="交易次数" value={String(snapshot.totals.tradeCount)} />
                  </div>
                </section>
              </div>

              <section className="panel">
                <div className="section-title">
                  <h2>集中度</h2>
                </div>
                <div className="allocation-list">
                  {topPositions.length ? (
                    topPositions.map((position) => (
                      <div className="allocation-row" key={position.symbol}>
                        <div>
                          <strong>{position.symbol}</strong>
                          <span>{formatMoney(position.marketValueCents, currency)}</span>
                        </div>
                        <div className="bar">
                          <span style={{ width: `${Math.min(100, position.allocation * 100)}%` }} />
                        </div>
                        <b>{formatPercent(position.allocation)}</b>
                      </div>
                    ))
                  ) : (
                    <Empty label="暂无持仓" />
                  )}
                </div>
              </section>
            </section>
          ) : null}

          {activeTab === "trades" ? (
            <section className="trade-layout">
              <div className="form-column">
                <TradeForm busy={busy} onSubmit={submitForm} />
                <PriceForm busy={busy} onSubmit={submitForm} />
                <CashFlowForm busy={busy} onSubmit={submitForm} />
              </div>
              <div className="stack">
                <section className="panel">
                  <div className="section-title">
                    <h2>交易记录</h2>
                    <span>{snapshot.trades.length}</span>
                  </div>
                  <TradesTable snapshot={snapshot} onDelete={remove} />
                </section>
                <section className="panel">
                  <div className="section-title">
                    <h2>资金流水</h2>
                    <span>{snapshot.cashFlows.length}</span>
                  </div>
                  <CashFlowTable snapshot={snapshot} onDelete={remove} />
                </section>
              </div>
            </section>
          ) : null}

          {activeTab === "journal" ? (
            <section className="journal-layout">
              <JournalForm busy={busy} onSubmit={submitForm} />
              <section className="panel">
                <div className="section-title">
                  <h2>交易日志</h2>
                  <span>{snapshot.journals.length}</span>
                </div>
                <JournalList snapshot={snapshot} onDelete={remove} />
              </section>
            </section>
          ) : null}

          {activeTab === "data" ? (
            <section className="data-layout">
              <AccountForm snapshot={snapshot} busy={busy} onSubmit={submitForm} />
              <section className="panel">
                <div className="section-title">
                  <h2>数据</h2>
                </div>
                <div className="data-actions">
                  <a className="button secondary" href="/api/export">
                    <Download size={17} />
                    导出 JSON
                  </a>
                  <button className="button ghost" type="button" onClick={() => refresh()}>
                    <RefreshCw size={17} />
                    刷新
                  </button>
                </div>
                <div className="stat-list compact">
                  <StatRow label="账户" value={snapshot.account.name} />
                  <StatRow label="币种" value={snapshot.account.currency} />
                  <StatRow label="初始资金" value={formatMoney(snapshot.account.initialCashCents, currency)} />
                  <StatRow label="持仓数量" value={String(snapshot.totals.openPositionCount)} />
                </div>
              </section>
            </section>
          ) : null}
        </>
      )}
    </main>
  );
}

function Metric({
  icon,
  label,
  value,
  detail,
  tone
}: {
  icon: ReactNode;
  label: string;
  value: string;
  detail?: string;
  tone?: string;
}) {
  return (
    <div className={`metric ${tone ?? ""}`}>
      <div className="metric-top">
        <div className="metric-icon">{icon}</div>
        <span>{label}</span>
      </div>
      <strong>{value}</strong>
      {detail ? <em>{detail}</em> : null}
    </div>
  );
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="stat-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Empty({ label }: { label: string }) {
  return <div className="empty">{label}</div>;
}

function presentMoney(value: number | null | undefined, currency: string) {
  return value === null || value === undefined ? null : formatMoney(value, currency);
}

function presentNumber(value: number | null | undefined, digits = 2) {
  return value === null || value === undefined ? null : formatNumber(value, digits);
}

function TradeForm({
  busy,
  onSubmit
}: {
  busy: boolean;
  onSubmit: SubmitHandler;
}) {
  const [instrument, setInstrument] = useState("stock");
  const isOption = instrument === "option";

  return (
    <section className="panel">
      <div className="section-title">
        <h2>新增交易</h2>
        <Plus size={18} />
      </div>
      <form className="form" onSubmit={(event) => onSubmit(event, "/api/trades")}>
        <div className="row two">
          <Field label="日期" name="tradeDate" type="date" defaultValue={today()} />
          <Field label={isOption ? "标的代码" : "代码"} name="symbol" placeholder="NVDA" />
        </div>
        <div className="row two">
          <label>
            <span>品种</span>
            <select name="instrument" value={instrument} onChange={(event) => setInstrument(event.target.value)}>
              <option value="stock">股票</option>
              <option value="etf">ETF</option>
              <option value="option">期权</option>
              <option value="crypto">Crypto</option>
              <option value="fund">基金</option>
              <option value="other">其他</option>
            </select>
          </label>
          <label>
            <span>方向</span>
            <select name="side" defaultValue="BUY">
              <option value="BUY">买入</option>
              <option value="SELL">卖出</option>
            </select>
          </label>
        </div>
        {isOption ? (
          <div className="form-section">
            <h3>期权合约</h3>
            <div className="row two">
              <label>
                <span>类型</span>
                <select name="optionType" defaultValue="CALL">
                  <option value="CALL">CALL</option>
                  <option value="PUT">PUT</option>
                </select>
              </label>
              <Field label="到期日" name="expirationDate" type="date" />
            </div>
            <div className="row two">
              <Field label="行权价" name="strike" type="number" step="0.01" />
              <Field label="合约乘数" name="contractMultiplier" type="number" step="1" defaultValue="100" />
            </div>
            <div className="row">
              <Field label="标的别名" name="underlyingSymbol" placeholder="可选，默认同标的代码" />
            </div>
          </div>
        ) : null}
        <div className="row three">
          <Field label={isOption ? "合约数" : "数量"} name="quantity" type="number" step="0.0001" />
          <Field label={isOption ? "权利金" : "价格"} name="price" type="number" step="0.0001" />
          <Field label="费用" name="fees" type="number" step="0.01" defaultValue="0" />
        </div>
        <div className="row two">
          <Field label="策略" name="strategy" placeholder="趋势 / 财报 / 事件" />
          <Field label="形态" name="setup" placeholder="突破 / 回踩 / 左侧" />
        </div>
        <Field label="标签" name="tags" placeholder="AI, earnings" />
        <label>
          <span>备注</span>
          <textarea name="notes" rows={3} />
        </label>
        <button className="button" type="submit" disabled={busy}>
          <Save size={17} />
          保存交易
        </button>
      </form>
    </section>
  );
}

function PriceForm({
  busy,
  onSubmit
}: {
  busy: boolean;
  onSubmit: SubmitHandler;
}) {
  return (
    <section className="panel">
      <div className="section-title">
        <h2>价格标记</h2>
      </div>
      <form className="form" onSubmit={(event) => onSubmit(event, "/api/price-marks")}>
        <div className="row three">
          <Field label="代码" name="symbol" placeholder="NVDA" />
          <Field label="日期" name="markedAt" type="date" defaultValue={today()} />
          <Field label="价格" name="price" type="number" step="0.0001" />
        </div>
        <input name="source" type="hidden" value="manual" />
        <button className="button secondary" type="submit" disabled={busy}>
          <Save size={17} />
          保存价格
        </button>
      </form>
    </section>
  );
}

function CashFlowForm({
  busy,
  onSubmit
}: {
  busy: boolean;
  onSubmit: SubmitHandler;
}) {
  return (
    <section className="panel">
      <div className="section-title">
        <h2>资金流水</h2>
      </div>
      <form className="form" onSubmit={(event) => onSubmit(event, "/api/cash-flows")}>
        <div className="row two">
          <Field label="日期" name="flowDate" type="date" defaultValue={today()} />
          <label>
            <span>类型</span>
            <select name="type" defaultValue="DEPOSIT">
              {Object.entries(cashFlowLabels).map(([value, label]) => (
                <option value={value} key={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="row two">
          <Field label="金额" name="amount" type="number" step="0.01" />
          <Field label="代码" name="symbol" placeholder="可选" />
        </div>
        <Field label="备注" name="notes" />
        <button className="button secondary" type="submit" disabled={busy}>
          <Save size={17} />
          保存流水
        </button>
      </form>
    </section>
  );
}

function JournalForm({
  busy,
  onSubmit
}: {
  busy: boolean;
  onSubmit: SubmitHandler;
}) {
  return (
    <section className="panel">
      <div className="section-title">
        <h2>新增日志</h2>
        <BookOpen size={18} />
      </div>
      <form className="form" onSubmit={(event) => onSubmit(event, "/api/journal")}>
        <div className="row two">
          <Field label="日期" name="entryDate" type="date" defaultValue={today()} />
          <Field label="标题" name="title" placeholder="交易复盘" />
        </div>
        <div className="row three">
          <Field label="代码" name="symbols" placeholder="NVDA, MSFT" />
          <Field label="情绪状态" name="mood" placeholder="冷静 / 犹豫 / 追涨" />
          <Field label="标签" name="tags" placeholder="risk, earnings" />
        </div>

        <div className="form-section">
          <h3>回测字段</h3>
          <div className="row three">
            <Field label="策略" name="strategy" placeholder="趋势 / 财报 / 事件" />
            <Field label="形态" name="setup" placeholder="突破 / 回踩 / 左侧" />
            <Field label="周期" name="timeframe" placeholder="日线 / 周线 / 30m" />
          </div>
          <div className="row three">
            <label>
              <span>方向</span>
              <select name="direction" defaultValue="LONG">
                <option value="LONG">做多</option>
                <option value="SHORT">做空</option>
                <option value="WATCH">观察</option>
              </select>
            </label>
            <label>
              <span>结果</span>
              <select name="result" defaultValue="OPEN">
                <option value="OPEN">进行中</option>
                <option value="WIN">盈利</option>
                <option value="LOSS">亏损</option>
                <option value="BREAKEVEN">打平</option>
                <option value="MISSED">错过</option>
              </select>
            </label>
            <label>
              <span>市场状态</span>
              <select name="marketRegime" defaultValue="uptrend">
                <option value="uptrend">上升趋势</option>
                <option value="downtrend">下降趋势</option>
                <option value="range">震荡</option>
                <option value="high_vol">高波动</option>
                <option value="low_vol">低波动</option>
                <option value="event">事件驱动</option>
              </select>
            </label>
          </div>
          <div className="row two">
            <Field label="催化因素" name="catalyst" placeholder="财报 / 降息 / 产品发布" />
            <Field label="信心评分 1-5" name="confidence" type="number" min="1" max="5" step="1" />
          </div>
        </div>

        <div className="form-section">
          <h3>交易计划</h3>
          <div className="row three">
            <Field label="计划入场" name="plannedEntry" type="number" step="0.0001" />
            <Field label="计划止损" name="plannedStop" type="number" step="0.0001" />
            <Field label="计划目标" name="plannedTarget" type="number" step="0.0001" />
          </div>
          <div className="row two">
            <Field label="计划风险金额" name="plannedRisk" type="number" step="0.01" />
            <Field label="计划仓位数量" name="plannedSize" type="number" step="0.0001" />
          </div>
        </div>

        <div className="form-section">
          <h3>实际结果</h3>
          <div className="row three">
            <Field label="实际入场" name="actualEntry" type="number" step="0.0001" />
            <Field label="实际退出" name="actualExit" type="number" step="0.0001" />
            <Field label="R 倍数" name="rMultiple" type="number" step="0.01" />
          </div>
          <div className="row two">
            <Field label="最高顺向价格" name="maxFavorable" type="number" step="0.0001" />
            <Field label="最大逆向价格" name="maxAdverse" type="number" step="0.0001" />
          </div>
          <div className="row three">
            <Field label="执行评分 1-5" name="executionScore" type="number" min="1" max="5" step="1" />
            <Field label="纪律评分 1-5" name="disciplineScore" type="number" min="1" max="5" step="1" />
            <label>
              <span>是否按计划</span>
              <select name="followedPlan" defaultValue="">
                <option value="">未评估</option>
                <option value="true">是</option>
                <option value="false">否</option>
              </select>
            </label>
          </div>
        </div>

        <label>
          <span>市场背景</span>
          <textarea name="marketContext" rows={3} />
        </label>
        <label>
          <span>交易假设</span>
          <textarea name="thesis" rows={3} />
        </label>
        <label>
          <span>计划</span>
          <textarea name="plan" rows={3} />
        </label>
        <label>
          <span>复盘</span>
          <textarea name="review" rows={3} />
        </label>
        <div className="row two">
          <label>
            <span>错误</span>
            <textarea name="mistakes" rows={3} />
          </label>
          <label>
            <span>经验</span>
            <textarea name="lessons" rows={3} />
          </label>
        </div>
        <button className="button" type="submit" disabled={busy}>
          <Save size={17} />
          保存日志
        </button>
      </form>
    </section>
  );
}

function AccountForm({
  snapshot,
  busy,
  onSubmit
}: {
  snapshot: PortfolioSnapshot;
  busy: boolean;
  onSubmit: SubmitHandler;
}) {
  return (
    <section className="panel">
      <div className="section-title">
        <h2>账户设置</h2>
      </div>
      <form className="form" onSubmit={(event) => onSubmit(event, "/api/account", "PATCH", false)}>
        <Field label="账户名" name="name" defaultValue={snapshot.account.name} />
        <div className="row two">
          <Field label="币种" name="currency" defaultValue={snapshot.account.currency} />
          <Field
            label="初始资金"
            name="initialCash"
            type="number"
            step="0.01"
            defaultValue={(snapshot.account.initialCashCents / 100).toFixed(2)}
          />
        </div>
        <button className="button" type="submit" disabled={busy}>
          <Save size={17} />
          保存账户
        </button>
      </form>
    </section>
  );
}

function Field({
  label,
  name,
  type = "text",
  ...props
}: {
  label: string;
  name: string;
  type?: string;
} & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label>
      <span>{label}</span>
      <input name={name} type={type} {...props} />
    </label>
  );
}

function PositionsTable({ snapshot }: { snapshot: PortfolioSnapshot }) {
  if (!snapshot.positions.length) return <Empty label="暂无持仓" />;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>代码</th>
            <th>品种</th>
            <th className="num">数量</th>
            <th className="num">成本</th>
            <th className="num">现价</th>
            <th className="num">市值</th>
            <th className="num">浮盈亏</th>
            <th className="num">占比</th>
          </tr>
        </thead>
        <tbody>
          {snapshot.positions.map((position) => (
            <tr key={position.symbol}>
              <td>
                <strong>{position.symbol}</strong>
              </td>
              <td>{instrumentLabels[position.instrument] ?? position.instrument}</td>
              <td className="num">{formatNumber(position.quantity, 4)}</td>
              <td className="num">{formatMoney(position.avgCostCents, snapshot.account.currency)}</td>
              <td className="num">{formatMoney(position.lastPriceCents, snapshot.account.currency)}</td>
              <td className="num">{formatMoney(position.marketValueCents, snapshot.account.currency)}</td>
              <td className={`num ${signedClass(position.unrealizedPnlCents)}`}>
                {formatMoney(position.unrealizedPnlCents, snapshot.account.currency)}
              </td>
              <td className="num">{formatPercent(position.allocation)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TradesTable({
  snapshot,
  onDelete
}: {
  snapshot: PortfolioSnapshot;
  onDelete: (endpoint: string) => void;
}) {
  if (!snapshot.trades.length) return <Empty label="暂无交易" />;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>日期</th>
            <th>代码</th>
            <th>品种</th>
            <th>方向</th>
            <th className="num">数量</th>
            <th className="num">价格</th>
            <th className="num">费用</th>
            <th>策略</th>
            <th>日志</th>
            <th className="tight"></th>
          </tr>
        </thead>
        <tbody>
          {snapshot.trades.map((trade) => (
            <tr key={trade.id}>
              <td>{trade.tradeDate}</td>
              <td>
                <strong>{trade.symbol}</strong>
              </td>
              <td>{instrumentLabels[trade.instrument] ?? trade.instrument}</td>
              <td>
                <span className={`pill ${trade.side === "BUY" ? "buy" : "sell"}`}>
                  {trade.side === "BUY" ? "买入" : "卖出"}
                </span>
              </td>
              <td className="num">{formatNumber(trade.quantity, 4)}</td>
              <td className="num">{formatMoney(trade.priceCents, snapshot.account.currency)}</td>
              <td className="num">{formatMoney(trade.feesCents, snapshot.account.currency)}</td>
              <td>{trade.strategy || "-"}</td>
              <td>
                {trade.journalCount ? <span className="chip muted">{trade.journalCount} 篇日志</span> : "-"}
              </td>
              <td className="tight">
                <button
                  className="icon-button danger"
                  type="button"
                  onClick={() => onDelete(`/api/trades/${trade.id}`)}
                  aria-label="删除交易"
                >
                  <Trash2 size={16} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CashFlowTable({
  snapshot,
  onDelete
}: {
  snapshot: PortfolioSnapshot;
  onDelete: (endpoint: string) => void;
}) {
  if (!snapshot.cashFlows.length) return <Empty label="暂无资金流水" />;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>日期</th>
            <th>类型</th>
            <th>代码</th>
            <th className="num">金额</th>
            <th>备注</th>
            <th className="tight"></th>
          </tr>
        </thead>
        <tbody>
          {snapshot.cashFlows.map((flow) => (
            <tr key={flow.id}>
              <td>{flow.flowDate}</td>
              <td>{cashFlowLabels[flow.type] ?? flow.type}</td>
              <td>{flow.symbol || "-"}</td>
              <td className="num">{formatMoney(flow.amountCents, snapshot.account.currency)}</td>
              <td>{flow.notes || "-"}</td>
              <td className="tight">
                <button
                  className="icon-button danger"
                  type="button"
                  onClick={() => onDelete(`/api/cash-flows/${flow.id}`)}
                  aria-label="删除资金流水"
                >
                  <Trash2 size={16} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function JournalList({
  snapshot,
  onDelete
}: {
  snapshot: PortfolioSnapshot;
  onDelete: (endpoint: string) => void;
}) {
  if (!snapshot.journals.length) return <Empty label="暂无日志" />;
  return (
    <div className="journal-list">
      {snapshot.journals.map((entry) => (
        <article className="journal-entry" key={entry.id}>
          <div className="journal-head">
            <div>
              <span>{entry.entryDate}</span>
              <h3>{entry.title}</h3>
            </div>
            <button
              className="icon-button danger"
              type="button"
              onClick={() => onDelete(`/api/journal/${entry.id}`)}
              aria-label="删除日志"
            >
              <Trash2 size={16} />
            </button>
          </div>
          <div className="chips">
            {entry.symbols.map((symbol) => (
              <span className="chip" key={symbol}>
                {symbol}
              </span>
            ))}
            {entry.tags.map((tag) => (
              <span className="chip muted" key={tag}>
                {tag}
              </span>
            ))}
            {entry.mood ? <span className="chip amber">{entry.mood}</span> : null}
            {entry.strategy ? <span className="chip">{entry.strategy}</span> : null}
            {entry.setup ? <span className="chip muted">{entry.setup}</span> : null}
            {entry.timeframe ? <span className="chip muted">{entry.timeframe}</span> : null}
            {entry.direction ? <span className="chip">{directionLabels[entry.direction] ?? entry.direction}</span> : null}
            {entry.result ? <span className="chip amber">{resultLabels[entry.result] ?? entry.result}</span> : null}
          </div>
          {entry.linkedTrades.length ? (
            <div className="linked-trades">
              <strong>关联交易</strong>
              <div>
                {entry.linkedTrades.map((trade) => (
                  <span className="linked-trade" key={trade.id}>
                    <b>{trade.symbol}</b>
                    <em>{trade.tradeDate}</em>
                    <i className={trade.side === "BUY" ? "positive" : "negative"}>
                      {trade.side === "BUY" ? "买入" : "卖出"} {formatNumber(trade.quantity, 4)} @{" "}
                      {formatMoney(trade.priceCents, snapshot.account.currency)}
                    </i>
                  </span>
                ))}
              </div>
            </div>
          ) : null}
          <JournalStructured entry={entry} currency={snapshot.account.currency} />
          <JournalBlock label="市场背景" value={entry.marketContext} />
          <JournalBlock label="交易假设" value={entry.thesis} />
          <JournalBlock label="计划" value={entry.plan} />
          <JournalBlock label="复盘" value={entry.review} />
          <div className="journal-two">
            <JournalBlock label="错误" value={entry.mistakes} />
            <JournalBlock label="经验" value={entry.lessons} />
          </div>
        </article>
      ))}
    </div>
  );
}

function JournalStructured({
  entry,
  currency
}: {
  entry: PortfolioSnapshot["journals"][number];
  currency: string;
}) {
  const contextRows = [
    ["策略", entry.strategy],
    ["形态", entry.setup],
    ["周期", entry.timeframe],
    ["方向", entry.direction ? directionLabels[entry.direction] ?? entry.direction : null],
    ["结果", entry.result ? resultLabels[entry.result] ?? entry.result : null],
    ["市场", entry.marketRegime ? marketRegimeLabels[entry.marketRegime] ?? entry.marketRegime : null],
    ["催化", entry.catalyst],
    ["信心", entry.confidence ? `${entry.confidence}/5` : null]
  ];

  const planRows = [
    ["计划入场", presentMoney(entry.plannedEntryCents, currency)],
    ["计划止损", presentMoney(entry.plannedStopCents, currency)],
    ["计划目标", presentMoney(entry.plannedTargetCents, currency)],
    ["计划风险", presentMoney(entry.plannedRiskCents, currency)],
    ["计划仓位", presentNumber(entry.plannedSize, 4)]
  ];

  const resultRows = [
    ["实际入场", presentMoney(entry.actualEntryCents, currency)],
    ["实际退出", presentMoney(entry.actualExitCents, currency)],
    ["R 倍数", entry.rMultiple === null || entry.rMultiple === undefined ? null : `${formatNumber(entry.rMultiple, 2)}R`],
    ["最高顺向", presentMoney(entry.maxFavorableCents, currency)],
    ["最大逆向", presentMoney(entry.maxAdverseCents, currency)],
    ["执行", entry.executionScore ? `${entry.executionScore}/5` : null],
    ["纪律", entry.disciplineScore ? `${entry.disciplineScore}/5` : null],
    [
      "按计划",
      entry.followedPlan === null || entry.followedPlan === undefined ? null : entry.followedPlan ? "是" : "否"
    ]
  ];

  const groups = [
    ["背景", contextRows],
    ["计划", planRows],
    ["结果", resultRows]
  ] as const;

  const visibleGroups = groups
    .map(([title, rows]) => [title, rows.filter(([, value]) => value)] as const)
    .filter(([, rows]) => rows.length);

  if (!visibleGroups.length) return null;

  return (
    <div className="journal-structured">
      {visibleGroups.map(([title, rows]) => (
        <div className="journal-facts" key={title}>
          <strong>{title}</strong>
          <div>
            {rows.map(([label, value]) => (
              <span key={label}>
                <em>{label}</em>
                <b>{value}</b>
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function JournalBlock({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null;
  return (
    <div className="journal-block">
      <strong>{label}</strong>
      <p>{value}</p>
    </div>
  );
}
