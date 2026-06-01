财报监控流程说明
每次执行时，请按固定流程读取仓库文件、补充最新信息、更新财务数据和投资跟踪结论。
仓库核心文件
1. company_list.md
公司列表文件。包含：
Claude 必须先读取这个文件，确认本次监控的公司范围。
2. financial_data.csv
财务数据表。建议字段包括：
company_name
ticker
market
segment
fiscal_period
report_date
revenue
revenue_yoy
revenue_qoq
gross_margin
operating_margin
net_income
eps
ai_related_revenue
data_center_revenue
ai_server_revenue
backlog
bookings
capex
guidance
source_url
last_updated
Claude 每次更新数据时，必须保留原有历史记录，不要覆盖历史季度数据。
3. earnings_analysis.md
财报分析文件。用于记录：
公司最新财报摘要
管理层原话
AI 相关业务进展
订单、backlog、capex、guidance
风险点
股价反应
与上一季度相比的变化
Claude 每次更新时，应在对应公司下新增一个日期小节。
4. watchlist_output.md
最终跟踪名单。Claude 每次执行后需要更新该文件，分成：
第一梯队：重点跟踪
第二梯队：有逻辑但需等待验证
第三梯队：已经反应充分
第四梯队：噪音较大或证据不足
5. research_log.md
研究日志。每次执行后必须记录：
执行日期
本次检查了哪些公司
新增了哪些财报或公告
更新了哪些数据
哪些公司结论发生变化
哪些信息缺失或需要人工确认
6. sources.md
来源文件。所有重要数据和结论必须记录来源链接，包括：
SEC EDGAR
公司 Investor Relations
HKEXnews
巨潮资讯
台湾 MOPS
交易所公告
Earnings call transcript
Reuters / Bloomberg / WSJ / Barron’s / CNBC / MarketWatch 等辅助来源

Claude 每次执行步骤
Step 1：读取文件
按以下顺序读取：
monitoring_workflow.md
company_list.md
financial_data.csv
earnings_analysis.md
watchlist_output.md
research_log.md
sources.md
如果某些文件不存在，请先创建空文件，并说明已创建。
Step 2：识别本次需要更新的公司
从 company_list.md 中读取公司池。
优先检查：
最近发布财报的公司
最近股价异动较大的公司
AI 服务器、HBM、AI PC、液冷、电力、光模块、PCB、连接器等核心环节公司
上次 research_log.md 中标记为“需要继续跟踪”的公司

Step 3：查找最新官方资料
原则：
官方财报和公司公告优先于新闻。
新闻只能作为辅助，不能替代原始财报。
如果无法找到官方来源，必须明确标记“未找到官方来源”。
不要把旧财报误认为最新财报。
不要只看新闻标题，必须检查正文或原始文件。

Step 4：提取财务和业务数据
每家公司至少提取：
最新财报季度
报告日期
总收入
同比增长
环比增长
毛利率
经营利润率
EPS
AI 相关收入
数据中心收入
AI 服务器收入
backlog / bookings
capex
下一季度或全年指引
管理层关于 AI、服务器、HBM、液冷、电力、光模块、数据中心的原话
股价财报后反应
主要风险
如果公司没有单独披露 AI 相关收入，请写：
“未单独披露 AI 相关收入，但管理层提到：……”
Step 5：更新 financial_data.csv
规则：
新季度数据新增一行。
不要覆盖旧季度数据。
如果某个字段没有披露，填写 “N/A”。
每一行必须有 source_url。
每一行必须更新 last_updated。

Step 6：更新 earnings_analysis.md
每家公司按以下模板新增内容：
## 公司名 / 股票代码

### YYYY-MM-DD 更新

#### 最新财报
- 财报季度：
- 报告日期：
- 收入：
- 同比：
- 毛利率：
- EPS：
- AI 相关收入：
- backlog / bookings：
- capex：
- guidance：

#### AI 相关业务
- 

#### 管理层原话
> 

#### 股价反应
- 

#### 投资逻辑
- 

#### 风险点
- 

#### 结论
- 分类：重点跟踪 / 等待验证 / 已反应充分 / 噪音较大
- 原因：
Step 7：更新 watchlist_output.md
按以下分类输出：
第一梯队：重点跟踪
标准：
AI 产业链核心瓶颈
有明确财务验证
管理层明确提到 AI 需求
订单、backlog、capex 或收入已经体现
估值和涨幅尚未完全透支，或有持续催化
第二梯队：有逻辑但需等待验证
标准：
产业链逻辑清晰
但财报披露不够明确
或订单尚未完全兑现
或需要等待下个季度确认
第三梯队：已经反应充分
标准：
股价已经大涨
估值明显抬升
市场预期较高
短期容易出现利好兑现
第四梯队：噪音较大
标准：
主要来自媒体解读或概念炒作
缺乏财务验证
缺乏订单、收入或管理层明确表述
股价反应和基本面因果关系不清晰

Step 8：更新 research_log.md
每次执行后追加：
## YYYY-MM-DD

### 本次检查公司
- 

### 新增财报 / 公告
- 

### 更新数据
- 

### 结论变化
- 

### 需要继续跟踪
- 

### 信息缺口
- 
输出要求
Claude 每次执行后，请输出：
本次更新摘要
更新了哪些文件
最重要的 5 个发现
新进入重点跟踪名单的公司
被降级为“已反应充分”或“噪音较大”的公司
需要人工确认的信息
下一次应优先检查的公司

重要规则
不要臆测财务数据。
不要用新闻标题替代财报原文。
不要删除历史数据。
不要覆盖原始分析，新增日期小节即可。
所有重要数据必须带来源。
如果数据不确定，必须标记“不确定”。
如果找不到最新官方资料，必须明确说明。
投资结论必须区分：财务验证、政策催化、市场情绪、估值风险。
不要只看美股，也要覆盖港股、A股、台股、日韩、欧洲。
每次更新都要记录 research_log.md。