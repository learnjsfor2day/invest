# 企业财务与隐含估值分析

一个独立的 Streamlit 应用：上传企业年度财务数据后，自动生成趋势图、计算盈利速度，并反推当前企业价值或股价隐含的未来收入增长。

未上传文件时，应用默认载入 PLTR 测试案例：

- 2022–2025：Palantir 年报 GAAP 实绩。
- 2026：Palantir Q1 2026 更新后的全年收入指引中值 76.56 亿美元。
- 2026 调整后自由现金流指引中值约 43 亿美元只写在来源备注中，不与历史 GAAP 自由现金流混算。
- 估值页默认使用用户给定的 3,080 亿美元企业价值、4.44 年持有期和 10% 年化回报要求。

## 启动

```bash
cd /Users/aibao/invest/enterprise-finance-app
/Users/aibao/invest/.venv/bin/pip install -r requirements.txt
/Users/aibao/invest/.venv/bin/streamlit run app.py --server.address 127.0.0.1 --server.port 8503
```

浏览器打开 `http://127.0.0.1:8503`。

## 上传格式

- 支持 `.csv` 和 `.xlsx`；Excel 文件读取第一个工作表。
- 模板中的金额统一使用“百万”，例如 `revenue=7700` 表示 77 亿；`share_price` 使用每股价格。
- `capex` 填资本开支的正数绝对值；如 `free_cash_flow` 留空，应用会按 `operating_cash_flow - abs(capex)` 自动补算。
- 最少需要 `company`、`fiscal_year`、`revenue` 三列。
- `is_estimate=true` 表示预测期。
- `source_note` 和 `source_url` 用于记录口径及来源。
- 页面内可下载 `templates/financial_data_template.csv`。

## 核心口径

- 盈利速度：收入 CAGR、收入增长加速度、营业利润率/净利率/自由现金流率变化、增量利润率、Rule of 40。
- 估值反推：根据要求回报率计算目标终值，再结合终值 FCF 倍数和终值 FCF 率反推所需自由现金流、收入和收入 CAGR。
- 可直接输入当前企业价值，也可由“当前股价 × 稀释后股数 + 债务 − 现金”推导企业价值，并按股东要求回报反推目标权益价值和目标企业价值。

这是一套情景分析工具，不构成投资建议。企业价值口径若直接按要求回报率复利，隐含假设净债务变化不影响股东回报；需要更严格口径时请选择“由当前股价推导”模式。
