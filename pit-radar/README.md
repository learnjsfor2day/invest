# 美股 Point-in-Time 数据库第一版

`pit-radar` 是一个面向美股研究的 Point-in-Time 数据底座，支持每日级数据采集、不可覆盖快照、as-of 回放、中文只读 Streamlit 检查页，以及只读的投资观察雷达。观察雷达不生成交易指令。

核心验收标准：

```text
任意 cutoff_time 下，只返回系统在当时实际已经 fetched 的数据。
后续更新、历史回补、ticker 变化和数据修订不能污染历史视角。
```

## 快速启动

当前本地 SQLite 演示库和 Streamlit 看板启动方式：

```bash
cd /Users/aibao/invest/pit-radar
DATABASE_URL='sqlite+pysqlite:///data/demo/pit_radar.sqlite' /Users/aibao/invest/.venv/bin/streamlit run src/pit_radar/ui/app.py --server.address 127.0.0.1 --server.port 8501
```

浏览器打开：

```text
http://127.0.0.1:8501
```

如果 `8501` 已被占用，通常说明看板已经在运行，直接打开上面的地址即可。

从零初始化开发环境：

```bash
cd pit-radar
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
docker compose up -d
pit-radar db upgrade
pit-radar ingest mock-estimates --mode live
pit-radar ingest mock-daily-bars --mode live
pit-radar ingest mock-earnings --mode live
pit-radar query estimates-as-of --ticker MU --cutoff "2026-07-14T09:30:00-04:00"
pit-radar ui
```

真实 FMP 采集前，在 `.env` 填：

```text
FMP_API_KEY=你的Key
FMP_AUTH_MODE=query
FMP_RATE_LIMIT_PER_MINUTE=540
FMP_MAX_RETRIES=2
```

FMP 手册标注限速为 600 次/分钟。客户端默认使用 540 次/分钟作为本地保护阈值，给网关和重试留一点缓冲；如果触发 429，会等待后自动重试。`FMP_MAX_RETRIES` 默认总尝试 2 次，避免冷门 ticker 或临时网关问题拖垮整轮任务；股票池 screener 会单独使用总尝试 3 次。

然后运行：

```bash
pit-radar ingest fmp-estimates --symbols MU,AAPL,NVDA --mode live
pit-radar ingest fmp-daily-bars --symbols MU,AAPL,NVDA --mode live --from-date 2026-07-01 --to-date 2026-07-14
pit-radar ingest fmp-earnings --symbols MU,AAPL,NVDA --mode live
pit-radar ingest fmp-news --symbols MU,AAPL,NVDA --mode live
pit-radar ingest fmp-financials --symbols MU,AAPL,NVDA --mode live
pit-radar ingest fmp-sec-filings --symbols MU,AAPL,NVDA --mode live --form-types 8-K --from-date 2026-07-01 --to-date 2026-07-14
pit-radar ingest fmp-transcripts --symbols MU --mode live --periods 2025:4
pit-radar ingest fmp-macro-calendar --countries US --from-date 2026-07-14 --to-date 2026-07-14 --mode live
```

## 每日采集

第一版用系统 cron/launchd 触发 CLI 即可，不引入任务队列。每天美股收盘后可以跑：

```bash
cd /Users/aibao/invest/pit-radar
source /Users/aibao/invest/.venv/bin/activate
python scripts/daily_fmp_batch.py --trade-date 2026-07-13 --tasks prices
```

## 基本面拐点雷达

`基本面拐点雷达`与原有预测次日开盘到收盘的实验性机会雷达相互独立。它面向
20/60/120 个交易日的中期研究候选，使用透明的规则评分：

- 盈利预期上修：30%
- 基本面加速：25%
- 价格与成交确认：20%
- 估值空间：15%
- 行业与评级催化：10%
- 高波动、弱资产负债表和价值陷阱额外扣分

生成当天候选榜：

```bash
cd /Users/aibao/invest/pit-radar
DATABASE_URL='sqlite+pysqlite:///data/demo/pit_radar.sqlite' \
  /Users/aibao/invest/.venv/bin/python scripts/build_inflection_watchlist.py
```

输出保存在 `data/inflection_radar/`。每次运行都会冻结一份历史评分截面；当未来
20/60/120 个交易日成熟后，脚本自动计算股票收益、行业中性超额收益和候选命中率。
Streamlit 的「基本面拐点雷达」页面读取最近一次结果。

中期价格特征需要至少 120 个交易日历史。首次使用先回填核心池三年日线；命令支持
断点续跑，已覆盖的股票会跳过：

```bash
python scripts/backfill_price_history.py --from-date 2023-01-01 --dry-run
python scripts/backfill_price_history.py --from-date 2023-01-01
```

雷达在积累足够的成熟标签前固定标记为 `observation_only`，不输出买卖指令。

`scripts/daily_fmp_batch.py` 默认读取 `data/universe/core_symbols.txt`；如果文件不存在，则退回 `.env` 的 `DEFAULT_SYMBOLS`。核心池文件一行一个 ticker。日常价格采集只拉这份核心池在指定交易日的一天日线，不做全美股全量，也默认不重复请求公司 profile，所以约等于每只股票 1 次 FMP 请求。

北京 `2026-07-14` 跑美国 `2026-07-13` 数据时：

```bash
python scripts/daily_fmp_batch.py --trade-date 2026-07-13 --tasks prices --chunk-size 50 --max-workers 8
```

先检查任务量、不实际调用 FMP：

```bash
python scripts/daily_fmp_batch.py --trade-date 2026-07-13 --tasks prices --dry-run
```

价格任务默认开启断点续跑：数据库里已经有该交易日日线的 ticker 会自动跳过；每轮结束后会对仍缺失的 ticker 重试 2 轮。需要强制生成新的 PIT 版本时再加 `--no-resume`。`--max-workers` 控制 chunk 内并发请求数，仍受 `FMP_RATE_LIMIT_PER_MINUTE` 全局限速保护。

`pit-radar ingest daily-snapshot` 仍保留给小股票池使用。它会一次性采集：分析师预期、日线行情、财报日历、纽约当天新闻/公告、当日 8-K 文件；不要直接拿它跑大股票池。

当前仓库已提供 macOS launchd 定时任务：

```bash
launchd/install_launchd_tasks.sh
```

安装后：

- `com.aibao.pitradar.daily`：每天北京时间 07:30 自动跑 `scripts/run_daily_fmp_once.sh`，采集上一个纽约交易日的核心池日线价格。
- `com.aibao.pitradar.estimates`：每天北京时间 09:20 自动跑 `scripts/run_estimates_snapshot_once.sh`，只采集核心池的分析师 EPS/营收预期、目标价和评级快照；已覆盖标的也会重新请求，PIT 表只在内容哈希变化时追加新版本。只有无数据、不支持或失败冷却中的 ticker 会按 coverage 规则跳过；如需临时续跑未完成部分，可设置 `PIT_RADAR_ESTIMATES_SKIP_COMPLETED_COVERAGE=1`。
- `com.aibao.pitradar.macro`：北京时间 07:05、20:40、22:10 自动跑 `scripts/run_macro_calendar_once.sh`，刷新美国宏观日历窗口并捕捉实际值、预期、前值修订。
- `com.aibao.pitradar.macro-reminder`：每天北京时间 07:20 自动跑 `scripts/run_macro_reminder_once.sh`，直接查询数据库里未来 3 天 High impact 宏观事件，通过飞书机器人推送一次性提醒。
- `com.aibao.pitradar.earnings`：每天北京时间 08:10 和 22:10 自动跑 `scripts/run_earnings_events_once.sh`，根据财报日历找核心池里临近披露的公司，只对这些公司拉财报事件包。
- `com.aibao.pitradar.universe`：每月 1 日和 15 日北京时间 08:30 自动跑 `scripts/run_universe_refresh_once.sh`，先刷新候选股票池，再生成 1500 支核心池并回填核心池公司基础信息。
- `com.aibao.pitradar.valuation-radar`：每天北京时间 10:30 冻结价值低谷/高估风险观察仓和全市场 PIT 分数，持续积累 20/60 个交易日的前向标签。
- `com.aibao.pitradar.inflection-radar`：每天北京时间 10:45 生成基本面拐点 Top20，冻结全市场评分并持续积累 20/60/120 个交易日的行业中性标签。

也可以在 Streamlit 的「任务看板」->「任务设置」里开关任务、修改执行时间并同步到 launchd。配置文件是：

```text
config/task_schedule.json
```

手动从配置同步 launchd：

```bash
scripts/sync_launchd_schedule.py --print-summary
```

查看状态：

```bash
launchctl list | grep com.aibao.pitradar
tail -f logs/launchd_pitradar_daily.out
tail -f logs/launchd_pitradar_estimates.out
tail -f logs/launchd_pitradar_macro.out
tail -f logs/launchd_pitradar_macro_reminder.out
tail -f logs/launchd_pitradar_earnings.out
tail -f logs/launchd_pitradar_universe.out
```

卸载定时任务：

```bash
launchd/uninstall_launchd_tasks.sh
```

## 股票池

每日价格、分析师预测和财报事件任务默认只使用 1500 支核心池，不扫描全部美股。完整刷新命令：

```bash
scripts/run_universe_refresh_once.sh
```

只刷新候选池时：

```bash
python scripts/refresh_fmp_universe.py --force
```

只从现有候选池重建核心池时：

```bash
python scripts/build_core_universe.py --size 1500
```

默认规则：

- 只保留 `NASDAQ`、`NYSE`、`AMEX` 上市标的；默认不按公司注册地过滤，所以 ADR 和境外注册但在美上市的公司也会进入候选。
- 排除 ETF、基金、非活跃交易标的、权证、单位股、优先股、票据、SPAC shell company 等非普通股结构。
- 目标至少 `4000` 只股票，screener 默认 `limit=1000`，通常 4 到 5 页即可拉够候选，减少长分页带来的随机连接断裂窗口。
- screener 单页默认超时 `30s`、总尝试 `3` 次；如果某页仍失败，会在 3 到 5 秒后额外重试失败页 2 轮。
- 市值至少 `20M USD`。
- 成交量至少 `3K` 股。
- 股价至少 `1 USD`。
- `price * volume` 至少 `20K USD`，过滤最差的低流动性票；策略回测时可再做更严格的本地二次筛。
- 默认不额外跑报价校验，避免 FMP `batch-quote` 临时断连导致大批候选被误删；如需校验，可加 `--validation-method batch-quote`，如需严格验证某天日线，可加 `--validation-method daily-bar --price-validation-date YYYY-MM-DD`。

输出文件：

| 文件 | 用途 |
|---|---|
| `data/universe/core_symbols.txt` | 生产采集任务读取的一行一个 ticker，默认 1500 支 |
| `data/universe/core_universe.csv` | 核心池明细，按市值、成交额、成交量、价格排序 |
| `data/universe/core_universe_excluded.csv` | 候选池里未进入核心池或被核心规则剔除的标的 |
| `data/universe/core_manifest.json` | 核心池生成时间、阈值和数量统计 |
| `data/universe/daily_symbols.txt` | 候选池 ticker 列表，不再作为生产采集默认输入 |
| `data/universe/daily_universe.csv` | 候选股票池明细 |
| `data/universe/daily_universe_rejected.csv` | 被过滤标的和原因 |
| `data/universe/refresh_manifest.json` | 生成时间、阈值、数量统计 |

建议用 cron/launchd 在每月 1 日和 15 日刷新一次。每日任务会读取 `core_manifest.json`，超过 14 天会提示刷新。
刷新脚本默认要求至少入选 4000 只股票才会写入文件，避免 FMP 网关临时失败时把股票池刷得过窄。

刷新股票池后，可以用本地 CSV 回填公司基础信息和快照指标，不额外调用 FMP：

```bash
scripts/run_universe_profile_backfill_once.sh
```

它会从核心池 `core_universe.csv` 更新 `core.security` 的公司名、交易所、行业、板块、国家，并写入 `market_cap`、`profile_price`、`average_volume`、`dollar_volume` 四类指标，避免页面里大面积显示 `Unknown` 或空指标。

需要把股票池补到类似 `MU` 的资料完整度时，运行 FMP enrichment 批量任务：

```bash
scripts/run_fmp_enrichment_once.sh --tasks estimates,earnings,financials,news,sec_filings --chunk-size 40 --max-workers 12 --news-limit 10 --sec-limit 10
```

该任务默认读取核心池。它会按模块断点续跑：已有对应模块数据的 ticker 自动跳过；确认无数据、暂不支持或暂时失败的 ticker 会写入 `raw.dataset_coverage`，在下次允许重试前不会反复打 API。`--max-workers` 控制同一 chunk 内并发处理的股票数，所有 FMP 请求仍受 `FMP_RATE_LIMIT_PER_MINUTE` 全局限速保护。批量 enrichment 默认不重复拉公司 `profile`，因为基础信息已由股票池 CSV 回填；如需强制刷新 profile，可加 `--include-profile`。如果要忽略覆盖状态强制再试，可加 `--ignore-coverage`。默认补分析师预期/评级、财报日历、财务事实、最近新闻和最近一年 SEC 文件。电话会原文需要明确财年季度，不做全股票盲拉。

## 回测特征宽表

原始 PIT 表负责保存可追溯版本；真正回测时，建议先生成每日 as-of 特征宽表。默认 cutoff 是对应美股交易日的纽约时间 09:30，即开盘决策口径：

```bash
DATABASE_URL='sqlite+pysqlite:///data/demo/pit_radar.sqlite' \
python scripts/build_daily_asof_features.py --trade-date 2026-07-17
```

输出：

```text
data/features/daily_asof_features_2026-07-17.csv
```

宽表只会关联 `trade_date <= 决策日` 且 `fetched_at <= cutoff` 的最近一根已知价格，以及相同 cutoff 下可见的最新分析师 EPS/营收预期、目标价和评级分布。`price_trade_date` 会明确标出价格属于哪一个交易日；开盘决策时不会再输出收盘后才抓到的当日价格。

### 价值低谷 / 高估风险观察仓（主雷达）

主雷达回答的是中期投资研究问题，而不是预测下一交易日涨跌：

- `value_trough`：同行估值和自身历史估值较低，同时财务质量合格、预期未明显恶化。
- `overvaluation_risk`：同行估值偏高或显著高于自身历史，价格/预期/质量支撑不足时风险分更高。

运行：

```bash
DATABASE_URL='sqlite+pysqlite:///data/demo/pit_radar.sqlite' \
/Users/aibao/invest/.venv/bin/python scripts/build_valuation_watchlists.py
```

输出写入 `data/valuation_radar/`：

- `value_trough_watchlist_<signal-date>.csv`：优质低估观察仓。
- `overvaluation_watchlist_<signal-date>.csv`：高估风险观察仓。
- `valuation_radar_<signal-date>.csv`：全部合格标的的分项分数、估值和理由。
- `valuation_radar_report_<signal-date>.json`：PIT 审计、评分定义和 20/60 交易日前向评估状态。
- `history/valuation_scores_*.csv`：每日冻结的信号快照，用于标签成熟后的 walk-forward 训练。

FMP 的季度财务报表可能是财年累计口径，雷达不会把四个季度直接相加。当前估值使用最近已披露的 FMP 估值倍数，并按当前 PIT 市值相对披露期市值的变化重新锚定。每次运行只使用 `fetched_at <= as_of` 且 `accepted_at <= as_of` 的事实。

PIT 信号积累满 20/60 个交易日之前，系统只输出透明的规则组合分数，并明确标记为 `observation_only`；不能把尚未成熟的未来收益倒灌成训练标签。成熟信号日达到最少样本数后，才适合训练并进行扩展窗口 walk-forward 回测。

### 次日机会雷达（短线实验，非当前主雷达）

严格 PIT 的第一版机会雷达使用“前一交易日收盘后生成特征、下一交易日开盘买入、当日收盘评估”的口径。模型不做随机拆分，而是按交易日扩展训练窗口；每个回测日只能使用当时已经抓到的历史标签。运行：

```bash
DATABASE_URL='sqlite+pysqlite:///data/demo/pit_radar.sqlite' \
python scripts/train_opportunity_radar.py
```

输出写入 `data/radar/`：

- `opportunity_radar_<signal-date>.csv`：最新全市场雷达分数和解释。
- `opportunity_radar_backtest_<signal-date>.csv`：逐日滚动回测。
- `opportunity_radar_audit_<signal-date>.csv`：每个信号日的 cutoff、标签覆盖率和泄漏检查。
- `opportunity_radar_model_<signal-date>.json`：模型系数、参数、回测汇总和防泄漏规则。

当前 PIT 历史很短时，模型文件会明确标记为实验性结果。不要把少量回测日的高收益外推成年化收益，也不要据此直接满仓交易。

coverage 默认重试节奏：

| 模块 | 无数据后多久再试 |
|---|---|
| `news` | 1 天 |
| `estimates` / `earnings` | 7 天 |
| `sec_filings` | 14 天 |
| `financials` | 30 天 |

网络断连、超时、429 等暂时失败会按 1 到 7 天退避重试；接口明确空返回不会无意义重复重试。

财报发布日或财报后补事实数据时跑：

```bash
pit-radar ingest earnings-event-snapshot --symbols MU,AAPL,NVDA --mode live --filings-from 2026-07-01 --filings-to 2026-07-14
```

`earnings-event-snapshot` 会采集：财报日历、三大表、财务比率、关键指标、增长指标、财务评分、新闻/公告、8-K/10-Q/10-K 文件。财报事实数据不需要每天全量快照，按财报事件或定期低频补采更合适。

定时任务使用 `scripts/run_earnings_events_once.sh`：

- 最多每 18 小时刷新一次核心池财报日历，保证 `expected_report_date` 不太旧。
- 每次运行时只选择纽约当前日期前后窗口内的财报公司，默认窗口是 `NY today - 1` 到 `NY today + 1`。
- 只对这些事件公司采集 earnings calendar、financials、新闻/公告、8-K/10-Q/10-K。
- 同一 ticker 默认 9 小时内不会重复跑事件包，避免手动触发或系统唤醒导致重复请求；PIT 表本身仍按内容哈希去重，内容不变不会重复插入。
- 日志写入 `logs/earnings_events_*.log`，最近状态写入 `logs/earnings_events.status`。

电话会原文按财报事件采集，不进入每日采集任务；需要明确季度，避免系统盲猜浪费请求：

```bash
pit-radar ingest fmp-transcripts --symbols MU --mode live --periods 2025:4
pit-radar ingest earnings-event-snapshot --symbols MU --mode live --transcript-periods 2025:4
```

管理层展望、Outlook、Guidance 暂不批量抽取。系统先把新闻稿、8-K 链接、电话会全文作为 PIT 来源材料存好，后续做深度分析时再按需抽取。

## 宏观日历

CPI、PPI、非农、初请、FOMC 等宏观数据使用单独命令刷新，不进入股票 `daily-snapshot`：

```bash
pit-radar ingest fmp-macro-calendar --countries US --mode live
pit-radar ingest fmp-macro-calendar --countries US --from-date 2026-07-14 --to-date 2026-07-14 --mode live
```

不传日期时默认从纽约今天开始取未来 14 天，用于定期更新事件日历；重要数据公布前后可以只刷当天窗口。宏观事件按 `event_key + payload_hash` 去重：完全没变化不插入，实际值、预期、前值、影响等级、公布时间或其他原始字段变化都会插入新快照。

定时任务使用 `scripts/run_macro_calendar_once.sh`，默认每次只请求一次 FMP economic calendar：

- 07:05 北京时间：刷新未来日历，并复核上一纽约交易日夜间后的宏观数据。
- 20:40 北京时间：覆盖常见 CPI、PPI、非农、初请等 8:30 ET 公布窗口。
- 22:10 北京时间：覆盖 ISM、JOLTS、成屋销售等 10:00 ET 左右公布窗口。

宏观事件提醒使用 `scripts/run_macro_reminder_once.sh`：

- 直接从 `pit.macro_event_snapshot` 查询每个 `event_key` 的最新版本，再按 `release_at_utc` 筛选未来窗口，不使用静态日程。
- 默认提醒未来 3 天、美国、High impact 事件。
- 提醒状态记录在 `logs/macro_event_reminders.json`，同一事件同一公布时间不会重复推送。
- 飞书机器人配置写在 `.env`，字段是 `FEISHU_WEBHOOK_URL` 和可选 `FEISHU_BOT_SECRET`。

首次配置飞书机器人 webhook：

```bash
scripts/configure_feishu_bot.sh
```

本地 dry-run 检查将推送什么内容：

```bash
PIT_RADAR_MACRO_REMINDER_DRY_RUN=1 PIT_RADAR_MACRO_REMINDER_IGNORE_STATE=1 scripts/run_macro_reminder_once.sh
```

## 来源原文

`pit.source_document_snapshot` 用来保存可追溯的来源材料：

- 新闻/新闻稿：FMP 返回 `text/summary/content` 时会 gzip 存到 `data/raw/source_documents/...`，同时保存原文链接。
- SEC 文件：先保存 `finalLink`/`link` 原文链接和元数据；不强制下载 SEC HTML，避免日常任务过慢或被 SEC 限流。
- 电话会：FMP 返回的全文会 gzip 存到 `data/raw/source_documents/earning_transcript/...`。

数据库只保存 `object_uri`、`content_hash`、`source_url` 和文本预览；完整正文从 `object_uri` 读取。

## 数据分层

| Schema | 用途 |
|---|---|
| `core` | 证券主体、历史 ticker、数据源、指标定义 |
| `raw` | 采集任务、原始响应元数据、采集覆盖状态 |
| `pit` | 清洗后的 Point-in-Time 快照 |

原始 JSON 不写入 PostgreSQL 大字段，而是 gzip 保存到本地：

```text
data/raw/{dataset}/{source}/{year}/{month}/{day}/{hash}.json.gz
```

数据库只保存 `object_uri`、`content_hash`、来源和获取时间。

FMP 接口和字段映射见：[docs/FMP_FIELD_MAPPING.md](docs/FMP_FIELD_MAPPING.md)。

## PIT 时间字段

| 英文字段 | 中文名 | 说明 |
|---|---|---|
| `event_at` | 事件时间 | 事件实际发生或指标对应时间 |
| `source_published_at` | 来源发布时间 | 数据源声称的发布时间 |
| `fetched_at` | 系统获取时间 | 系统实际成功取得数据的时间，严格 PIT 以它判断可见性 |
| `recorded_at` | 入库时间 | 数据写入数据库的时间 |

严格 PIT 查询默认只使用：

```sql
fetched_at <= :cutoff_time
AND ingest_run.collection_mode = 'live'
```

## 核心表

| 表 | 说明 |
|---|---|
| `core.security` | 证券主体，不用 ticker 做主键 |
| `core.security_identifier` | ticker、CIK、FIGI、CUSIP 等历史标识符 |
| `core.data_source` | 数据源定义 |
| `core.metric_definition` | 通用指标定义 |
| `raw.ingest_run` | 每次采集任务 |
| `raw.payload` | 原始响应元数据和 gzip 文件路径 |
| `raw.dataset_coverage` | 每个数据集/股票的覆盖状态，用于断点续跑和避免无数据 ticker 反复请求 |
| `pit.estimate_snapshot` | EPS/营收预期快照 |
| `pit.analyst_snapshot` | 目标价与评级分布快照 |
| `pit.earnings_calendar_snapshot` | 财报日期快照 |
| `pit.daily_market_bar` | 日线行情版本 |
| `pit.news_item_snapshot` | 新闻与公告事件快照 |
| `pit.financial_fact_snapshot` | 财报、财务比率、关键指标、增长指标和评分事实快照 |
| `pit.sec_filing_snapshot` | SEC 文件链接与元数据快照 |
| `pit.earning_transcript_snapshot` | 财报电话会全文快照 |
| `pit.source_document_snapshot` | 新闻稿、SEC文件、电话会等来源原文或原文链接 |
| `pit.macro_event_snapshot` | 宏观经济日历事件快照 |
| `pit.metric_observation` | 暂无专用表的通用指标 |

## 去重策略

不是所有 PIT 数据都按同一种方式保存，但原则一致：内容不变不重复入库，内容变化才追加新版本。`fetched_at` 仍保存为严格 PIT 可见时间，但不再单独制造重复版本。

- 分析师预期、评级、财报日历、通用指标：业务字段哈希不变时跳过；EPS、营收、评级、日期等变化时插入新快照。
- 日线行情：同一交易日同内容跳过；价格、成交量等发生修订时追加 `revision_no` 新版本。
- 财务事实：按证券、数据集、周期、报告期和内容哈希去重；主表只保存核心字段，完整 FMP 响应保存在 `raw.payload` 指向的 gzip 文件中。
- 新闻按 `security_id + news_type + url` 去重；没有 URL 时按 `title + published_at` 去重。
- SEC 文件优先按 `final_url` 去重，没有则按 `filing_url`，再退回 `form_type + accepted_at`。
- 电话会原文按 `security_id + fiscal_year + fiscal_period` 去重。
- 来源原文按 `security_id + document_type + document_key` 去重。
- 宏观事件按 `event_key + payload_hash` 去重。
- `daily-snapshot` 默认只采纽约当天新闻，避免每天把旧新闻重复写入。

检查历史库里是否已有完全重复快照：

```bash
python scripts/cleanup_duplicate_pit_snapshots.py --tables all
```

确认只删除同业务键、同 `data_hash` 的 exact duplicate 后再执行：

```bash
python scripts/cleanup_duplicate_pit_snapshots.py --tables daily_market_bar --execute
```

## CLI

```bash
pit-radar db upgrade
pit-radar ingest mock-estimates --mode live
pit-radar ingest mock-daily-bars --mode live
pit-radar ingest mock-earnings --mode live
pit-radar ingest fmp-estimates --symbols MU,AAPL --mode live
pit-radar ingest fmp-news --symbols MU,AAPL --mode live --from-date 2026-07-14 --to-date 2026-07-14
pit-radar ingest fmp-financials --symbols MU,AAPL --mode live --periods annual,quarter --limit 8
pit-radar ingest fmp-sec-filings --symbols MU,AAPL --mode live --form-types 8-K,10-Q,10-K
pit-radar ingest fmp-transcripts --symbols MU --mode live --periods 2025:4
pit-radar ingest fmp-macro-calendar --countries US --mode live
pit-radar ingest daily-snapshot --symbols MU,AAPL --mode live
pit-radar ingest earnings-event-snapshot --symbols MU,AAPL --mode live
pit-radar query estimates-as-of --ticker MU --cutoff "2026-07-14T09:30:00-04:00"
pit-radar query earnings-as-of --ticker MU --cutoff "2026-07-14T09:30:00-04:00"
pit-radar dictionary export --format markdown --output DATA_DICTIONARY.md
pit-radar ui
```

## 当前限制

- 第一版只保存日线，不保存分钟线、盘口或逐笔成交。
- FMP stable API 当前没有可靠的期权 IV、借券费率、short interest 接口；系统已在 `core.metric_definition` 预留 `option_iv`、`borrow_fee`、`short_interest`，后续接专门数据源。
- FMP Collector 已实现基础接口，但字段解析采用宽松映射，首次接入新接口时需要用 raw payload 校验字段名。
- 严格 PIT 只能保证本系统开始采集后的 live 数据可回放；历史补数必须标记为 `backfill`。
- Streamlit 页面只读，不提供任何修改或删除 PIT 数据的能力。
