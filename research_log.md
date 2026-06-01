# 研究日志

## 2026-05-31

### 本次检查公司
- GOOGL(Alphabet)— company_list.jsonl 第 1 行
- MSFT(Microsoft)— company_list.jsonl 第 2 行
- 范围说明:测试阶段,仅覆盖前 2 家

### 新增财报 / 公告
- GOOGL 2026 Q1 财报(报告日 2026-04-29)
- MSFT FY26 Q3 财报(报告日 2026-04-29)

### 更新数据
- `financial_data.csv` 新增 2 行(GOOGL Q1 / MSFT FY26Q3)
- `earnings_analysis.md` 新增 2 段公司分析
- `watchlist_output.md` 新建梯队结构,2 家进入第一梯队
- `sources.md` 新增 2 条来源

### 结论变化
- GOOGL → 第一梯队(首次纳入):RPO/Cloud/capex 三重共振
- MSFT → 第一梯队(首次纳入):AI run rate $37B 罕见明确披露 + 容量不足
- 跨公司共振:两家同日同步抬高 capex,产业链上游需求验证

### 需要继续跟踪
- GOOGL Cloud RPO 是否能在 2026 Q2 维持高位
- MSFT Microsoft Cloud GM(目前 66%)是否继续下行
- 受益的下游公司财报:AVGO、TSM、ANET、VRT、SK 海力士、MU(下次扩展时优先)

### 信息缺口
- **管理层原话**:本次靠搜索摘要,需查 earnings call transcript 与 8-K 原文核对(GOOGL/MSFT 都有此问题)
- **股价反应**:4/29 盘后及 4/30 走势未取,需补
- **MSFT commercial RPO 数字**:8-K 中应有,本次未提取
- **GOOGL 整体 GM、MSFT 整体 GM 与净利润**:本次摘要未含,需补
- **revenue_qoq**:两家均未填(需对比上一季度数据)
- 数据来源目前依赖二手汇总(stocktitan、marketscreener、investing 等),官方一手 PDF/8-K 未直读,后续需要切换到 SEC EDGAR / abc.xyz / microsoft.com IR 直读

### 下次执行优先项
1. 把 GOOGL/MSFT 的官方 PR + earnings call transcript 直读一遍,补齐管理层原话与缺口字段
2. 扩展到 company_list 的 3-7 行(META、AMZN、AAPL、CRM、NOW),完成 hyperscaler capex 同步图谱
3. 随后启动产业链上游验证组:AVGO、TSM、NVDA、ANET、VRT
