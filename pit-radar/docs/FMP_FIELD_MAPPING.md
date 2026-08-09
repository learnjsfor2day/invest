# FMP 字段映射

本项目只使用 FMP `/stable/` 接口。严格 PIT 可见性仍以本系统 `fetched_at` 为准，FMP 字段中的日期只作为业务时间、报告期或来源更新时间。

live 采集时，原始响应会完整保存到 `raw.payload` 对应的 gzip 文件；写入 PIT 表时，`estimate_snapshot` 和 `earnings_calendar_snapshot` 默认只保留采集日当天及之后的记录。这样可以避免首次接入 FMP 时，把已经过去、且可能被数据源事后修订过的历史预期当作可用于回测的快照。确实需要补历史时，应使用 `backfill` 模式单独标记，严格 PIT 查询默认不会使用 backfill。

新闻、SEC 文件、电话会原文属于事件材料，不按每日快照重复保存。新闻采集支持 `from/to` 日期过滤，`daily-snapshot` 默认只保留纽约当天新闻；电话会原文只在显式 `fmp-transcripts` 或带 `--transcript-periods` 的财报事件采集中获取；入库时再按 URL 或事件主键去重。

宏观经济日历属于市场事件，不进入股票每日快照。使用 `fmp-macro-calendar` 定期刷新未来窗口，公布日前后再刷新当天窗口；同一个事件只有来源 payload 发生变化时才插入新快照。

来源原文统一写入 `pit.source_document_snapshot`：有正文时 gzip 存到 `data/raw/source_documents/...`，数据库保存 `object_uri`；只有官方链接时保存 `source_url` 和元数据。

## 采集接口

| CLI | FMP endpoint | Raw payload key | 说明 |
|---|---|---|---|
| `pit-radar ingest fmp-estimates` | `/stable/analyst-estimates` | `estimates` | EPS、营收等分析师预期，同时拉 `annual` 和 `quarter` |
| `pit-radar ingest fmp-estimates` | `/stable/price-target-consensus` | `price_target` | 目标价一致预期 |
| `pit-radar ingest fmp-estimates` | `/stable/price-target-summary` | `price_target_summary` | 目标价历史汇总 |
| `pit-radar ingest fmp-estimates` | `/stable/grades-consensus` | `grades_consensus` | 买入/持有/卖出评级分布 |
| `pit-radar ingest fmp-estimates` | `/stable/ratings-snapshot` | `ratings_snapshot` | FMP 综合评级与评分 |
| `pit-radar ingest fmp-daily-bars` | `/stable/historical-price-eod/full` | `historical` | 日线行情 |
| `pit-radar ingest fmp-earnings` | `/stable/earnings` | `earnings` | 财报日期、EPS/营收预期 |
| `pit-radar ingest fmp-news` | `/stable/news/stock` | `news` | 股票新闻，支持本地按 `publishedDate` 过滤日期 |
| `pit-radar ingest fmp-news` | `/stable/news/press-releases` | `news` | 公司公告，支持本地按 `publishedDate` 过滤日期 |
| `pit-radar ingest fmp-sec-filings` | `/stable/sec-filings-search/symbol` | `sec_filings` | SEC文件搜索，默认保存8-K |
| `pit-radar ingest fmp-transcripts` | `/stable/earning-call-transcript` | `transcripts` | 财报电话会原文 |
| `pit-radar ingest fmp-macro-calendar` | `/stable/economic-calendar` | `events` | 宏观经济日历，例如 CPI、PPI、就业和央行事件 |
| `pit-radar ingest fmp-financials` | `/stable/income-statement` | `financials.income_statement` | 利润表 |
| `pit-radar ingest fmp-financials` | `/stable/balance-sheet-statement` | `financials.balance_sheet` | 资产负债表 |
| `pit-radar ingest fmp-financials` | `/stable/cash-flow-statement` | `financials.cash_flow` | 现金流量表 |
| `pit-radar ingest fmp-financials` | `/stable/ratios` | `financials.ratios` | 财务比率 |
| `pit-radar ingest fmp-financials` | `/stable/key-metrics` | `financials.key_metrics` | 关键指标 |
| `pit-radar ingest fmp-financials` | `/stable/financial-growth` | `financials.financial_growth` | 增长指标 |
| `pit-radar ingest fmp-financials` | `/stable/financial-scores` | `financials.financial_scores` | 财务评分 |
| 所有 FMP collector | `/stable/profile` | `profile` | 公司画像、CIK、CUSIP、ISIN、市值等 |

## `pit.estimate_snapshot`

| FMP 字段 | PIT 字段 | 说明 |
|---|---|---|
| `symbol` | `security_id` | 通过 `core.security_identifier` 映射为内部 ID |
| `date` | `fiscal_period_end` | FMP analyst-estimates 的报告期日期 |
| collector 注入的 `period` | `period_type` | `annual` -> `fiscal_year`，`quarter` -> `quarter` |
| `epsAvg` | `eps_mean` | EPS 预期均值 |
| `epsHigh` | `eps_high` | EPS 预期最高值 |
| `epsLow` | `eps_low` | EPS 预期最低值 |
| `numAnalystsEps` | `analyst_count_eps` | EPS 预测机构数 |
| `revenueAvg` | `revenue_mean` | 营收预期均值 |
| `revenueHigh` | `revenue_high` | 营收预期最高值 |
| `revenueLow` | `revenue_low` | 营收预期最低值 |
| `numAnalystsRevenue` | `analyst_count_revenue` | 营收预测机构数 |
| `profile.currency` | `currency` | 交易货币，缺失默认 USD |

## `pit.analyst_snapshot`

| FMP 字段 | PIT 字段 | 说明 |
|---|---|---|
| `price_target.targetConsensus` | `target_mean` | 目标价一致预期 |
| `price_target.targetHigh` | `target_high` | 目标价最高值 |
| `price_target.targetLow` | `target_low` | 目标价最低值 |
| `grades_consensus.strongBuy` | `strong_buy_count` | 强烈买入数量 |
| `grades_consensus.buy` | `buy_count` | 买入数量 |
| `grades_consensus.hold` | `hold_count` | 持有数量 |
| `grades_consensus.sell` | `sell_count` | 卖出数量 |
| `grades_consensus.strongSell` | `strong_sell_count` | 强烈卖出数量 |

## `pit.earnings_calendar_snapshot`

| FMP 字段 | PIT 字段 | 说明 |
|---|---|---|
| `date` | `expected_report_date` | 预计财报日 |
| `fiscalDateEnding` | `fiscal_period_end` | 如果 FMP 未返回，则临时使用 `date` 并写入 `quality_flags` |
| `time` | `expected_report_session` | `bmo` -> 盘前，`amc` -> 盘后，其它为未知 |
| `epsEstimated` | `estimated_eps` | 财报日历 EPS 预期 |
| `revenueEstimated` | `estimated_revenue` | 财报日历营收预期 |
| `epsActual` | `actual_eps` | 财报实际 EPS |
| `revenueActual` | `actual_revenue` | 财报实际营收 |
| `epsSurprise` / `surprise` | `eps_surprise` | EPS 超预期值 |
| `epsSurprisePercent` / `surprisePercentage` | `eps_surprise_percent` | EPS 超预期百分比 |
| `revenueSurprise` | `revenue_surprise` | 营收超预期值 |
| `revenueSurprisePercent` | `revenue_surprise_percent` | 营收超预期百分比 |
| `lastUpdated` | `source_published_at` / `quality_flags.fmp_last_updated` | collector 会尽量写入来源更新时间 |

## `pit.daily_market_bar`

| FMP 字段 | PIT 字段 | 说明 |
|---|---|---|
| `date` | `trade_date` | 美股交易日期 |
| `open` | `open` | 开盘价 |
| `high` | `high` | 最高价 |
| `low` | `low` | 最低价 |
| `close` | `close` | 收盘价 |
| `adjClose` / `adjustedClose` | `adjusted_close` | 如果 FMP 当前接口不返回，则保持空值 |
| `volume` | `volume` | 成交量 |

FMP 当前还可能返回 `vwap`、`change`、`changePercent`。第一版日线表按需求不保存 VWAP、bid、ask、tick，这些字段暂不入表。

## `pit.news_item_snapshot`

| FMP 字段 | PIT 字段 | 说明 |
|---|---|---|
| 请求 symbol | `security_id` | 通过 `core.security_identifier` 映射为内部 ID |
| collector 注入的 `_news_type` | `news_type` | `stock_news` 或 `press_release` |
| `title` / `headline` | `title` | 新闻标题 |
| `url` / `link` | `url` | 原文链接 |
| `site` / `publisher` / `source` | `publisher` | 发布方 |
| `author` | `author` | 作者 |
| `publishedDate` / `date` | `published_at` / `source_published_at` | 新闻发布时间 |
| `text` / `summary` / `content` | `summary` | 摘要或正文片段 |
| `image` / `imageUrl` | `image_url` | 图片链接 |
| `sentiment` | `sentiment_label` | 若来源返回情绪标签则保存 |
| `sentimentScore` | `sentiment_score` | 若来源返回情绪分数则保存 |

去重键：优先使用 `security_id + news_type + url`；缺少 URL 时使用 `security_id + news_type + title + published_at`。同一新闻第二天再次被 FMP 返回时不会重复入库。

同时写入 `pit.source_document_snapshot`：`text` / `summary` / `content` 作为可存正文，`url` / `link` 作为 `source_url`。

## `pit.financial_fact_snapshot`

财报事实数据先以通用事实表保存整行 JSON，避免第一版把数百个财务字段过早物化。后续雷达因子稳定后，再把高频使用字段抽成专用列或宽表。

| FMP endpoint | `dataset_code` | 关键周期字段 |
|---|---|---|
| `/stable/income-statement` | `income_statement` | `date`, `period`, `calendarYear`, `reportedCurrency`, `acceptedDate`, `filingDate` |
| `/stable/balance-sheet-statement` | `balance_sheet` | 同上 |
| `/stable/cash-flow-statement` | `cash_flow` | 同上 |
| `/stable/ratios` | `ratios` | `date`, `period`, `calendarYear` |
| `/stable/key-metrics` | `key_metrics` | `date`, `period`, `calendarYear` |
| `/stable/financial-growth` | `financial_growth` | `date`, `period`, `calendarYear` |
| `/stable/financial-scores` | `financial_scores` | 通常缺少标准报告期，缺失时 `period_type=unknown` 并写入 `quality_flags` |

| FMP 字段 | PIT 字段 | 说明 |
|---|---|---|
| 请求 symbol | `security_id` | 通过 `core.security_identifier` 映射为内部 ID |
| endpoint 类型 | `dataset_code` | 财务数据集代码 |
| `period` | `period_type` / `fiscal_period` | `annual` -> `fiscal_year`，`quarter` -> `quarter` |
| `date` | `fiscal_period_end` | 报告期结束日 |
| `calendarYear` | `fiscal_year` | 财年 |
| `reportedCurrency` / `currency` | `reported_currency` | 报表货币 |
| `filingDate` / `fillingDate` | `filing_date` | 文件披露日期 |
| `acceptedDate` | `accepted_at` / `source_published_at` | 文件接受时间 |
| 整行 JSON | `value_json` | 保留来源原始字段，供后续因子抽取 |

## `pit.sec_filing_snapshot`

| FMP 字段 | PIT 字段 | 说明 |
|---|---|---|
| `symbol` | `security_id` | 通过 `core.security_identifier` 映射为内部 ID |
| `formType` | `form_type` | SEC 表格类型，例如 8-K、10-Q、10-K |
| `filingDate` | `filing_date` | 文件披露日期 |
| `acceptedDate` | `accepted_at` / `source_published_at` | SEC 接受时间 |
| `cik` | `cik` | SEC CIK |
| `link` | `filing_url` | SEC filing index 链接 |
| `finalLink` | `final_url` | 最终文件链接，8-K 附件和财报新闻稿常从这里继续追溯 |
| `hasFinancials` | `has_financials` | FMP 标记是否包含财务数据 |
| 整行 JSON | `value_json` | 保留来源原始字段 |

去重键：优先使用 `final_url`，其次 `filing_url`，最后使用 `form_type + accepted_at`。

同时写入 `pit.source_document_snapshot`：`finalLink` 优先作为 `source_url`，其次 `link`。第一版只保存官方原文链接和元数据，不批量下载 SEC HTML。

## `pit.earning_transcript_snapshot`

| FMP 字段 | PIT 字段 | 说明 |
|---|---|---|
| `symbol` | `security_id` | 通过 `core.security_identifier` 映射为内部 ID |
| `year` | `fiscal_year` | 电话会对应财年 |
| `period` | `fiscal_period` | 电话会对应季度，例如 Q4 |
| `date` | `call_date` / `source_published_at` | 电话会日期 |
| `content` | `transcript_text` | 电话会全文 |
| 系统计算 | `word_count` | 粗略词数，便于估算后续分析成本 |
| 除全文外的整行 JSON | `value_json` | 保留来源元数据 |

去重键：`security_id + fiscal_year + fiscal_period`。同一季度电话会重复采集不会重复入库。

同时写入 `pit.source_document_snapshot`：`content` 作为可存正文 gzip 落盘，`document_key=earning_transcript:{year}:{period}`。

## `pit.source_document_snapshot`

| 来源 | `document_type` | `document_key` | 原文存储 |
|---|---|---|---|
| 股票新闻 | `stock_news` | URL 或 `stock_news:{published_at}:{title}` | 有 `text/summary/content` 时 gzip 存本地，同时保存 URL |
| 公司新闻稿 | `press_release` | URL 或 `press_release:{published_at}:{title}` | 有 `text/summary/content` 时 gzip 存本地，同时保存 URL |
| SEC 文件 | `sec_filing` | `finalLink` / `link` / `form_type + accepted_at` | 保存官方链接和元数据，暂不批量下载 HTML |
| 电话会全文 | `earning_transcript` | `earning_transcript:{year}:{period}` | `content` gzip 存本地 |

| 字段 | 说明 |
|---|---|
| `source_url` | 原文链接，可以直接追溯到新闻、公告或 SEC 文件 |
| `object_uri` | 本地 gzip 原文路径，只有获取到文本正文时填写 |
| `content_hash` | 原文 SHA256 |
| `text_excerpt` | 文本预览，便于 UI 快速检查 |
| `metadata_json` | 来源文档附加字段 |

Guidance/Outlook 先不批量抽取。新闻稿、8-K 链接和电话会全文已按 PIT 存储，后续深度分析可以基于这些来源材料按需抽取，避免每日批量 LLM 消耗。

## `pit.macro_event_snapshot`

宏观事件使用独立命令采集，不按股票每日快照重复保存。不传日期时，`pit-radar ingest fmp-macro-calendar` 默认刷新纽约今天到未来 14 天；CPI、FOMC、就业等公布日前后可以指定当天窗口反复刷新，以记录预期、前值、实际值和公布时间修订。

| FMP 字段 | PIT 字段 | 说明 |
|---|---|---|
| `id` / `eventId` | `provider_event_id` | 若 FMP 返回稳定事件 ID，则优先用于生成 `event_key` |
| `event` / `eventName` / `title` | `event_name` | 英文事件名称 |
| 本地映射 | `event_name_cn` | 第一版先保留为空，后续可加中文别名表 |
| `country` | `country` | 国家或地区代码，CLI 默认只保留 `US` |
| `currency` | `currency` | 货币代码，例如 USD |
| `date` / `releaseDate` | `release_at_utc` | 计划或实际公布时间，统一转 UTC |
| `impact` / `importance` | `impact` | 事件重要程度 |
| `actual` | `actual_raw` / `actual_value` | 实际值原始文本和可解析数值 |
| `estimate` / `forecast` | `estimate_raw` / `estimate_value` | 市场预期原始文本和可解析数值 |
| `previous` | `previous_raw` / `previous_value` | 前值原始文本和可解析数值 |
| `unit` 或数值后缀 | `unit` | `%`、`K`、`M`、`B` 等 |
| 系统采集时间 | `observed_at_utc` | 本系统看到该版本数据的时间 |
| 采集模式 | `is_backfill` | `backfill` 模式写入 `true`，live 写入 `false` |
| 规范化整行 JSON | `payload_hash` | SHA256，用于判断这一版来源数据是否变化 |
| 整行 JSON | `raw_json` | FMP 原始事件 JSON |

`event_key` 生成规则：如果 FMP 返回稳定 ID，则使用 `fmp:{id}`；否则使用 `country + currency + event_name + release_date` 的稳定 hash。`observed_at_utc` 不参与 `event_key`。唯一约束是 `event_key + payload_hash`，所以同一事件完全没变不会重复入库；公布时间、实际值、预期值、前值、影响等级或任何原始字段变化，都会生成新的 `payload_hash` 并插入新快照。

## `pit.metric_observation`

| FMP 字段 | metric_code | 类型 | 说明 |
|---|---|---|---|
| `profile.marketCap` | `market_cap` | numeric | 市值 |
| `profile.price` | `profile_price` | numeric | profile 接口返回的快照价格 |
| `profile.beta` | `beta` | numeric | Beta |
| `profile.averageVolume` | `average_volume` | numeric | 平均成交量 |
| `price_target.targetMedian` | `analyst_target_median` | numeric | 目标价中位数 |
| `price_target_summary` | `analyst_target_summary` | json | 目标价历史汇总原始结构 |
| `grades_consensus.consensus` | `analyst_rating_consensus` | text | 分析师评级共识 |
| `ratings_snapshot.rating` | `fmp_rating` | text | FMP 综合评级 |
| `ratings_snapshot.overallScore` | `fmp_rating_overall_score` | numeric | FMP 综合评分 |
| `ratings_snapshot.*Score` | `fmp_rating_scores` | json | FMP 分项评分 |
| 预留 | `option_iv` | numeric | 期权 IV，FMP stable API 当前未提供 |
| 预留 | `borrow_fee` | numeric | 借券费率，需后续接入证券借贷或券商数据源 |
| 预留 | `short_interest` | numeric | 空头持仓量，FMP FAQ 表示当前不提供 |

## `core.security_identifier`

| FMP 字段 | identifier_type |
|---|---|
| `profile.symbol` / 请求 symbol | `ticker` |
| `profile.cik` | `cik` |
| `profile.cusip` | `cusip` |
| `profile.isin` | `isin` |
