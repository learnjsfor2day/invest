# 期权工作台

Streamlit 版期权工具，替代旧的 `index.html` 单页工具。数据默认只保存在本机：

- `data/trades.csv`：交易记录
- `data/reviews.csv`：交易复盘
- `data/account_snapshots.csv`：账户资金快照

## 启动

```bash
cd /Users/aibao/invest/options
/Users/aibao/invest/.venv/bin/streamlit run app.py --server.address 127.0.0.1 --server.port 8502
```

浏览器打开：

```text
http://127.0.0.1:8502
```

如果 `8502` 被占用，可以换端口：

```bash
/Users/aibao/invest/.venv/bin/streamlit run app.py --server.address 127.0.0.1 --server.port 8503
```

## 功能

- 持仓：汇总未平仓合约、成本、已实现盈亏和按当前权利金估值。
- 账户资金：记录账户净值、现金、购买力、占用资金、入金、出金和备注，生成账户曲线与资金净流入统计；也可以从持仓中选择合约平仓，填写卖出权利金后自动写入交易记录并同步账户资金快照。
- 买入计划：Black-Scholes 理论价、Greeks、盈亏平衡、健康度评分、仓位建议、情景矩阵，以及权利金止盈、权利金止损、标的失效价和时间止损规则。
- 卖出计划：支持卖出 PUT/CALL，计算收取权利金、盈亏平衡、买回止盈、买回止损、被行权价格、现金担保/备兑/券商保证金估算，并可同步账户资金。
- 策略组合：支持 1 到 4 条腿，自定义买卖、CALL/PUT、行权价、张数、权利金，计算到期 P&L。
- 交易记录：保存买入开仓、卖出平仓、卖出开仓、买入平仓记录，自动汇总已实现盈亏。
- 复盘看板：统计胜率、已实现盈亏、平均赢/亏、Profit Factor、问题标签、是否按计划执行和策略盈亏。

旧版 HTML 仍保留在：

```text
index.html
```
