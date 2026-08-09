# PIT Radar 数据字典

| 表 | 英文字段 | 中文名称 | 中文解释 | 数据类型 |
|---|---|---|---|---|
| core.data_source | `source_id` | 数据源ID | 数据来自哪个外部或内部数据源。 | `INTEGER` |
| core.data_source | `source_code` | 数据源代码 | 数据源代码 | `VARCHAR(64)` |
| core.data_source | `source_name` | 数据源名称 | 数据源名称 | `VARCHAR(128)` |
| core.data_source | `source_type` | 数据源类型 | 数据源类型 | `VARCHAR(64)` |
| core.data_source | `base_url` | 数据源基础URL | 数据源基础URL | `TEXT` |
| core.data_source | `timezone` | 数据源默认时区 | 数据源默认时区 | `VARCHAR(64)` |
| core.data_source | `priority` | 数据源优先级 | 数据源优先级 | `INTEGER` |
| core.data_source | `is_active` | 是否启用 | 是否启用 | `BOOLEAN` |
| core.data_source | `created_at` | 创建时间 | 创建时间 | `DATETIME` |
| core.data_source | `updated_at` | 更新时间 | 更新时间 | `DATETIME` |
| core.metric_definition | `metric_code` | 指标代码 | 指标代码 | `VARCHAR(64)` |
| core.metric_definition | `display_name_zh` | 中文展示名 | 中文展示名 | `VARCHAR(128)` |
| core.metric_definition | `description_zh` | 中文说明 | 中文说明 | `TEXT` |
| core.metric_definition | `value_type` | 值类型 | 值类型 | `VARCHAR(32)` |
| core.metric_definition | `unit` | 单位 | 单位 | `VARCHAR(32)` |
| core.metric_definition | `frequency` | 频率 | 频率 | `VARCHAR(32)` |
| core.metric_definition | `created_at` | 创建时间 | 创建时间 | `DATETIME` |
| core.metric_definition | `updated_at` | 更新时间 | 更新时间 | `DATETIME` |
| core.security | `security_id` | 证券内部ID | 系统内部稳定证券主键，不使用 ticker 作为外键。 | `INTEGER` |
| core.security | `company_name` | 公司名称 | 公司名称 | `VARCHAR(255)` |
| core.security | `primary_ticker` | 主要代码 | 当前用于展示的主要 ticker，历史回放应使用 security_identifier 判断当时有效代码。 | `VARCHAR(32)` |
| core.security | `exchange` | 交易所 | 交易所 | `VARCHAR(64)` |
| core.security | `cik` | SEC CIK | SEC CIK | `VARCHAR(32)` |
| core.security | `asset_type` | 资产类型 | 资产类型 | `VARCHAR(32)` |
| core.security | `sector` | 行业大类 | 行业大类 | `VARCHAR(128)` |
| core.security | `industry` | 细分行业 | 细分行业 | `VARCHAR(128)` |
| core.security | `currency` | 交易货币 | 交易货币 | `VARCHAR(16)` |
| core.security | `country` | 国家或地区 | 国家或地区 | `VARCHAR(64)` |
| core.security | `is_active` | 是否活跃 | 是否活跃 | `BOOLEAN` |
| core.security | `first_seen_at` | 首次发现时间 | 首次发现时间 | `DATETIME` |
| core.security | `last_seen_at` | 最近观察时间 | 最近观察时间 | `DATETIME` |
| core.security | `created_at` | 创建时间 | 创建时间 | `DATETIME` |
| core.security | `updated_at` | 更新时间 | 更新时间 | `DATETIME` |
| core.security_identifier | `identifier_id` | 标识符ID | 标识符ID | `INTEGER` |
| core.security_identifier | `security_id` | 证券内部ID | 系统内部稳定证券主键，不使用 ticker 作为外键。 | `INTEGER` |
| core.security_identifier | `identifier_type` | 标识符类型 | ticker、cik、figi、cusip、isin 或 vendor_symbol。 | `VARCHAR(32)` |
| core.security_identifier | `identifier_value` | 标识符取值 | 具体的 ticker、CIK 或供应商代码。 | `VARCHAR(128)` |
| core.security_identifier | `valid_from` | 生效时间 | 该标识符开始有效的时间。 | `DATETIME` |
| core.security_identifier | `valid_to` | 失效时间 | 该标识符失效的时间；为空表示当前仍有效。 | `DATETIME` |
| core.security_identifier | `source_id` | 数据源ID | 数据来自哪个外部或内部数据源。 | `INTEGER` |
| core.security_identifier | `created_at` | 创建时间 | 创建时间 | `DATETIME` |
| pit.analyst_snapshot | `analyst_snapshot_id` | 分析师快照ID | 分析师快照ID | `INTEGER` |
| pit.analyst_snapshot | `security_id` | 证券内部ID | 系统内部稳定证券主键，不使用 ticker 作为外键。 | `INTEGER` |
| pit.analyst_snapshot | `snapshot_at` | 快照时间 | 该条快照代表的业务观察时间，通常等于系统获取时间。 | `DATETIME` |
| pit.analyst_snapshot | `source_published_at` | 来源发布时间 | 外部数据源声称该信息正式发布的时间。 | `DATETIME` |
| pit.analyst_snapshot | `fetched_at` | 系统获取时间 | 系统实际成功取得该数据的时间，严格PIT回放以此判断数据是否可用。 | `DATETIME` |
| pit.analyst_snapshot | `target_mean` | 目标价均值 | 分析师目标价的均值或一致预期。 | `NUMERIC(24, 6)` |
| pit.analyst_snapshot | `target_high` | 目标价最高值 | 分析师目标价最高值。 | `NUMERIC(24, 6)` |
| pit.analyst_snapshot | `target_low` | 目标价最低值 | 分析师目标价最低值。 | `NUMERIC(24, 6)` |
| pit.analyst_snapshot | `strong_buy_count` | 强烈买入数量 | 评级分布中的强烈买入数量。 | `INTEGER` |
| pit.analyst_snapshot | `buy_count` | 买入数量 | 评级分布中的买入数量。 | `INTEGER` |
| pit.analyst_snapshot | `hold_count` | 持有数量 | 评级分布中的持有数量。 | `INTEGER` |
| pit.analyst_snapshot | `sell_count` | 卖出数量 | 评级分布中的卖出数量。 | `INTEGER` |
| pit.analyst_snapshot | `strong_sell_count` | 强烈卖出数量 | 评级分布中的强烈卖出数量。 | `INTEGER` |
| pit.analyst_snapshot | `source_id` | 数据源ID | 数据来自哪个外部或内部数据源。 | `INTEGER` |
| pit.analyst_snapshot | `raw_payload_id` | 原始载荷ID | 该清洗记录可追溯的原始响应元数据ID。 | `INTEGER` |
| pit.analyst_snapshot | `data_hash` | 标准化数据哈希 | 标准化数据哈希 | `VARCHAR(64)` |
| pit.analyst_snapshot | `quality_flags` | 数据质量标记 | 校验失败、异常跳变、映射失败、回补警告等信息。 | `JSON` |
| pit.analyst_snapshot | `recorded_at` | 入库时间 | 数据写入本系统数据库的时间。 | `DATETIME` |
| pit.daily_market_bar | `daily_bar_id` | 日线ID | 日线ID | `INTEGER` |
| pit.daily_market_bar | `security_id` | 证券内部ID | 系统内部稳定证券主键，不使用 ticker 作为外键。 | `INTEGER` |
| pit.daily_market_bar | `trade_date` | 交易日期 | 美股交易日期。 | `DATE` |
| pit.daily_market_bar | `open` | 开盘价 | 开盘价 | `NUMERIC(24, 6)` |
| pit.daily_market_bar | `high` | 最高价 | 最高价 | `NUMERIC(24, 6)` |
| pit.daily_market_bar | `low` | 最低价 | 最低价 | `NUMERIC(24, 6)` |
| pit.daily_market_bar | `close` | 收盘价 | 收盘价 | `NUMERIC(24, 6)` |
| pit.daily_market_bar | `adjusted_close` | 复权收盘价 | 数据源返回的复权收盘价。 | `NUMERIC(24, 6)` |
| pit.daily_market_bar | `volume` | 成交量 | 成交量 | `NUMERIC(30, 4)` |
| pit.daily_market_bar | `source_id` | 数据源ID | 数据来自哪个外部或内部数据源。 | `INTEGER` |
| pit.daily_market_bar | `source_published_at` | 来源发布时间 | 外部数据源声称该信息正式发布的时间。 | `DATETIME` |
| pit.daily_market_bar | `fetched_at` | 系统获取时间 | 系统实际成功取得该数据的时间，严格PIT回放以此判断数据是否可用。 | `DATETIME` |
| pit.daily_market_bar | `raw_payload_id` | 原始载荷ID | 该清洗记录可追溯的原始响应元数据ID。 | `INTEGER` |
| pit.daily_market_bar | `revision_no` | 修订版本号 | 同一证券同一交易日的日线数据版本号，修订时追加新版本。 | `INTEGER` |
| pit.daily_market_bar | `data_hash` | 标准化数据哈希 | 标准化数据哈希 | `VARCHAR(64)` |
| pit.daily_market_bar | `quality_flags` | 数据质量标记 | 校验失败、异常跳变、映射失败、回补警告等信息。 | `JSON` |
| pit.daily_market_bar | `recorded_at` | 入库时间 | 数据写入本系统数据库的时间。 | `DATETIME` |
| pit.earning_transcript_snapshot | `transcript_id` | 电话会原文快照ID | 电话会原文快照ID | `INTEGER` |
| pit.earning_transcript_snapshot | `security_id` | 证券内部ID | 系统内部稳定证券主键，不使用 ticker 作为外键。 | `INTEGER` |
| pit.earning_transcript_snapshot | `fiscal_year` | 财年 | 财年 | `INTEGER` |
| pit.earning_transcript_snapshot | `fiscal_period` | 财务期间，例如Q1/Q4 | 财务期间，例如Q1/Q4 | `VARCHAR(16)` |
| pit.earning_transcript_snapshot | `call_date` | 电话会日期 | 电话会日期 | `DATE` |
| pit.earning_transcript_snapshot | `transcript_text` | 电话会全文 | 电话会全文 | `TEXT` |
| pit.earning_transcript_snapshot | `word_count` | 全文词数 | 全文词数 | `INTEGER` |
| pit.earning_transcript_snapshot | `source_published_at` | 来源发布时间 | 外部数据源声称该信息正式发布的时间。 | `DATETIME` |
| pit.earning_transcript_snapshot | `fetched_at` | 系统获取时间 | 系统实际成功取得该数据的时间，严格PIT回放以此判断数据是否可用。 | `DATETIME` |
| pit.earning_transcript_snapshot | `value_json` | 来源电话会元数据JSON | 来源电话会元数据JSON | `JSON` |
| pit.earning_transcript_snapshot | `source_id` | 数据源ID | 数据来自哪个外部或内部数据源。 | `INTEGER` |
| pit.earning_transcript_snapshot | `raw_payload_id` | 原始载荷ID | 该清洗记录可追溯的原始响应元数据ID。 | `INTEGER` |
| pit.earning_transcript_snapshot | `data_hash` | 标准化数据哈希 | 标准化数据哈希 | `VARCHAR(64)` |
| pit.earning_transcript_snapshot | `quality_flags` | 数据质量标记 | 校验失败、异常跳变、映射失败、回补警告等信息。 | `JSON` |
| pit.earning_transcript_snapshot | `recorded_at` | 入库时间 | 数据写入本系统数据库的时间。 | `DATETIME` |
| pit.earnings_calendar_snapshot | `earnings_snapshot_id` | 财报日历快照ID | 财报日历快照ID | `INTEGER` |
| pit.earnings_calendar_snapshot | `security_id` | 证券内部ID | 系统内部稳定证券主键，不使用 ticker 作为外键。 | `INTEGER` |
| pit.earnings_calendar_snapshot | `fiscal_period_end` | 财报周期结束日 | 财务预测或财报事件对应的明确周期结束日期。 | `DATE` |
| pit.earnings_calendar_snapshot | `expected_report_date` | 预计财报日 | 当时已知的预计财报披露日期。 | `DATE` |
| pit.earnings_calendar_snapshot | `expected_report_session` | 预计披露时段 | before_open 盘前，after_close 盘后，during_market 盘中，unknown 未知。 | `VARCHAR(32)` |
| pit.earnings_calendar_snapshot | `estimated_eps` | 预计EPS | 财报日历中提供的预计每股收益。 | `NUMERIC(24, 6)` |
| pit.earnings_calendar_snapshot | `estimated_revenue` | 预计营收 | 财报日历中提供的预计营收。 | `NUMERIC(24, 6)` |
| pit.earnings_calendar_snapshot | `actual_eps` | 实际EPS | 实际EPS | `NUMERIC(24, 6)` |
| pit.earnings_calendar_snapshot | `actual_revenue` | 实际营收 | 实际营收 | `NUMERIC(24, 6)` |
| pit.earnings_calendar_snapshot | `eps_surprise` | EPS超预期值 | EPS超预期值 | `NUMERIC(24, 6)` |
| pit.earnings_calendar_snapshot | `eps_surprise_percent` | EPS超预期百分比 | EPS超预期百分比 | `NUMERIC(18, 8)` |
| pit.earnings_calendar_snapshot | `revenue_surprise` | 营收超预期值 | 营收超预期值 | `NUMERIC(24, 6)` |
| pit.earnings_calendar_snapshot | `revenue_surprise_percent` | 营收超预期百分比 | 营收超预期百分比 | `NUMERIC(18, 8)` |
| pit.earnings_calendar_snapshot | `snapshot_at` | 快照时间 | 该条快照代表的业务观察时间，通常等于系统获取时间。 | `DATETIME` |
| pit.earnings_calendar_snapshot | `source_published_at` | 来源发布时间 | 外部数据源声称该信息正式发布的时间。 | `DATETIME` |
| pit.earnings_calendar_snapshot | `fetched_at` | 系统获取时间 | 系统实际成功取得该数据的时间，严格PIT回放以此判断数据是否可用。 | `DATETIME` |
| pit.earnings_calendar_snapshot | `source_id` | 数据源ID | 数据来自哪个外部或内部数据源。 | `INTEGER` |
| pit.earnings_calendar_snapshot | `raw_payload_id` | 原始载荷ID | 该清洗记录可追溯的原始响应元数据ID。 | `INTEGER` |
| pit.earnings_calendar_snapshot | `data_hash` | 标准化数据哈希 | 标准化数据哈希 | `VARCHAR(64)` |
| pit.earnings_calendar_snapshot | `quality_flags` | 数据质量标记 | 校验失败、异常跳变、映射失败、回补警告等信息。 | `JSON` |
| pit.earnings_calendar_snapshot | `recorded_at` | 入库时间 | 数据写入本系统数据库的时间。 | `DATETIME` |
| pit.estimate_snapshot | `estimate_id` | 预期快照ID | 预期快照ID | `INTEGER` |
| pit.estimate_snapshot | `security_id` | 证券内部ID | 系统内部稳定证券主键，不使用 ticker 作为外键。 | `INTEGER` |
| pit.estimate_snapshot | `fiscal_period_end` | 财报周期结束日 | 财务预测或财报事件对应的明确周期结束日期。 | `DATE` |
| pit.estimate_snapshot | `period_type` | 周期类型 | quarter 表示季度，fiscal_year 表示财年。 | `VARCHAR(32)` |
| pit.estimate_snapshot | `snapshot_at` | 快照时间 | 该条快照代表的业务观察时间，通常等于系统获取时间。 | `DATETIME` |
| pit.estimate_snapshot | `source_published_at` | 来源发布时间 | 外部数据源声称该信息正式发布的时间。 | `DATETIME` |
| pit.estimate_snapshot | `fetched_at` | 系统获取时间 | 系统实际成功取得该数据的时间，严格PIT回放以此判断数据是否可用。 | `DATETIME` |
| pit.estimate_snapshot | `eps_mean` | EPS预期均值 | 分析师每股收益预期的平均值。 | `NUMERIC(24, 6)` |
| pit.estimate_snapshot | `eps_high` | EPS预期最高值 | 分析师每股收益预期的最高值。 | `NUMERIC(24, 6)` |
| pit.estimate_snapshot | `eps_low` | EPS预期最低值 | 分析师每股收益预期的最低值。 | `NUMERIC(24, 6)` |
| pit.estimate_snapshot | `analyst_count_eps` | EPS预测机构数量 | EPS预测机构数量 | `INTEGER` |
| pit.estimate_snapshot | `revenue_mean` | 营收预期均值 | 分析师营收预期平均值。 | `NUMERIC(24, 6)` |
| pit.estimate_snapshot | `revenue_high` | 营收预期最高值 | 分析师营收预期最高值。 | `NUMERIC(24, 6)` |
| pit.estimate_snapshot | `revenue_low` | 营收预期最低值 | 分析师营收预期最低值。 | `NUMERIC(24, 6)` |
| pit.estimate_snapshot | `analyst_count_revenue` | 营收预测机构数量 | 营收预测机构数量 | `INTEGER` |
| pit.estimate_snapshot | `currency` | 货币 | 货币 | `VARCHAR(16)` |
| pit.estimate_snapshot | `source_id` | 数据源ID | 数据来自哪个外部或内部数据源。 | `INTEGER` |
| pit.estimate_snapshot | `raw_payload_id` | 原始载荷ID | 该清洗记录可追溯的原始响应元数据ID。 | `INTEGER` |
| pit.estimate_snapshot | `data_hash` | 标准化数据哈希 | 标准化数据哈希 | `VARCHAR(64)` |
| pit.estimate_snapshot | `quality_flags` | 数据质量标记 | 校验失败、异常跳变、映射失败、回补警告等信息。 | `JSON` |
| pit.estimate_snapshot | `recorded_at` | 入库时间 | 数据写入本系统数据库的时间。 | `DATETIME` |
| pit.financial_fact_snapshot | `financial_fact_id` | 财务事实快照ID | 财务事实快照ID | `INTEGER` |
| pit.financial_fact_snapshot | `security_id` | 证券内部ID | 系统内部稳定证券主键，不使用 ticker 作为外键。 | `INTEGER` |
| pit.financial_fact_snapshot | `dataset_code` | 财务数据集代码 | 财务数据集代码 | `VARCHAR(64)` |
| pit.financial_fact_snapshot | `period_type` | 周期类型 | quarter 表示季度，fiscal_year 表示财年。 | `VARCHAR(32)` |
| pit.financial_fact_snapshot | `fiscal_period_end` | 财报周期结束日 | 财务预测或财报事件对应的明确周期结束日期。 | `DATE` |
| pit.financial_fact_snapshot | `fiscal_year` | 财年 | 财年 | `INTEGER` |
| pit.financial_fact_snapshot | `fiscal_period` | 财务期间，例如 Q1/FY | 财务期间，例如 Q1/FY | `VARCHAR(16)` |
| pit.financial_fact_snapshot | `reported_currency` | 报表货币 | 报表货币 | `VARCHAR(16)` |
| pit.financial_fact_snapshot | `filing_date` | 文件披露日期 | 文件披露日期 | `DATE` |
| pit.financial_fact_snapshot | `accepted_at` | 文件接受时间 | 文件接受时间 | `DATETIME` |
| pit.financial_fact_snapshot | `source_published_at` | 来源发布时间 | 外部数据源声称该信息正式发布的时间。 | `DATETIME` |
| pit.financial_fact_snapshot | `fetched_at` | 系统获取时间 | 系统实际成功取得该数据的时间，严格PIT回放以此判断数据是否可用。 | `DATETIME` |
| pit.financial_fact_snapshot | `value_json` | 财务核心字段JSON | 用于筛选和展示的轻量财务字段；FMP完整原始响应保存在 raw.payload 指向的 gzip 文件中。 | `JSON` |
| pit.financial_fact_snapshot | `source_id` | 数据源ID | 数据来自哪个外部或内部数据源。 | `INTEGER` |
| pit.financial_fact_snapshot | `raw_payload_id` | 原始载荷ID | 该清洗记录可追溯的原始响应元数据ID。 | `INTEGER` |
| pit.financial_fact_snapshot | `data_hash` | 标准化数据哈希 | 标准化数据哈希 | `VARCHAR(64)` |
| pit.financial_fact_snapshot | `quality_flags` | 数据质量标记 | 校验失败、异常跳变、映射失败、回补警告等信息。 | `JSON` |
| pit.financial_fact_snapshot | `recorded_at` | 入库时间 | 数据写入本系统数据库的时间。 | `DATETIME` |
| pit.macro_event_snapshot | `id` | 宏观事件快照ID | 宏观事件每个可见版本的内部主键；同一事件发生修订时会生成新的快照ID。 | `BIGINT` |
| pit.macro_event_snapshot | `source` | 数据源 | 宏观事件来自哪个供应商；当前固定为 FMP。 | `VARCHAR(32)` |
| pit.macro_event_snapshot | `provider_event_id` | 供应商事件ID | FMP 原始事件ID；如果接口提供稳定ID，会优先用于生成事件稳定键。 | `VARCHAR(128)` |
| pit.macro_event_snapshot | `event_key` | 事件稳定键 | 用于识别同一个宏观事件的稳定唯一键，不包含本系统观察时间；同一事件修订时仍应尽量保持一致。 | `VARCHAR(128)` |
| pit.macro_event_snapshot | `event_name` | 英文事件名称 | FMP 返回的英文宏观事件名称，例如 CPI YoY、Core CPI MoM 或 Fed Speech。 | `VARCHAR(255)` |
| pit.macro_event_snapshot | `event_name_cn` | 中文事件名称 | 事件中文别名；第一版允许为空，后续可通过本地事件名称映射表补齐。 | `VARCHAR(255)` |
| pit.macro_event_snapshot | `country` | 国家/地区 | 宏观事件所属国家或地区；美股雷达主要关注 US。 | `VARCHAR(64)` |
| pit.macro_event_snapshot | `currency` | 货币代码 | 事件关联货币，例如 USD；用于区分同名跨市场宏观事件。 | `VARCHAR(16)` |
| pit.macro_event_snapshot | `release_at_utc` | 公布时间UTC | FMP 当时给出的计划或实际公布时间，统一转为 UTC；公布时间调整会作为新版本快照保留。 | `DATETIME` |
| pit.macro_event_snapshot | `impact` | 重要程度 | FMP 对宏观事件的影响等级，例如 High、Medium、Low；用于交易前过滤高影响事件。 | `VARCHAR(32)` |
| pit.macro_event_snapshot | `actual_raw` | 实际值原文 | 数据公布后的实际值原始文本，保留百分号、K/M/B 等来源格式，便于追溯和展示。 | `VARCHAR(128)` |
| pit.macro_event_snapshot | `estimate_raw` | 预期值原文 | 市场一致预期或预测值原始文本，用于计算宏观数据是否超预期。 | `VARCHAR(128)` |
| pit.macro_event_snapshot | `previous_raw` | 前值原文 | 上一期公布值或修正后前值的原始文本；前值修订会产生新的 payload_hash。 | `VARCHAR(128)` |
| pit.macro_event_snapshot | `actual_value` | 实际值数值 | 从实际值原文中解析出的数值，便于排序、计算预期差和后续回测。 | `NUMERIC(24, 8)` |
| pit.macro_event_snapshot | `estimate_value` | 预期值数值 | 从预期值原文中解析出的数值；百分比按显示数值保存，例如 3.5% 保存为 3.5。 | `NUMERIC(24, 8)` |
| pit.macro_event_snapshot | `previous_value` | 前值数值 | 从前值原文中解析出的数值；无法解析时保留为空但 raw 字段仍保存。 | `NUMERIC(24, 8)` |
| pit.macro_event_snapshot | `unit` | 单位 | 解析出的单位或数量级，例如 %、K、M、B；用于展示和预期差解释。 | `VARCHAR(32)` |
| pit.macro_event_snapshot | `observed_at_utc` | 系统观察时间UTC | 本系统实际获取到这一版宏观事件数据的时间；严格 PIT 回测以此判断当时是否已知。 | `DATETIME` |
| pit.macro_event_snapshot | `is_backfill` | 是否历史回填 | 标记该快照是否由 backfill 模式写入；严格 PIT 回测默认只使用 live 快照。 | `BOOLEAN` |
| pit.macro_event_snapshot | `payload_hash` | 原始载荷哈希 | 规范化后的单条宏观事件 JSON 的 SHA256；与 event_key 组成唯一约束，避免完全重复入库。 | `VARCHAR(64)` |
| pit.macro_event_snapshot | `raw_json` | FMP原始JSON | FMP 返回的完整宏观事件原始字段；任何原始字段变化都会形成新的 payload_hash。 | `JSON` |
| pit.macro_event_snapshot | `source_id` | 数据源ID | 内部数据源表主键，用于把宏观事件快照追溯到 FMP 数据源配置。 | `INTEGER` |
| pit.macro_event_snapshot | `raw_payload_id` | 原始载荷ID | 对应 raw.payload 的原始响应ID，可回看当次 FMP 请求窗口和 gzip 原始文件。 | `INTEGER` |
| pit.macro_event_snapshot | `created_at` | 入库时间 | 该宏观事件快照写入本地数据库的时间。 | `DATETIME` |
| pit.metric_observation | `observation_id` | 观察值ID | 观察值ID | `INTEGER` |
| pit.metric_observation | `security_id` | 证券内部ID | 系统内部稳定证券主键，不使用 ticker 作为外键。 | `INTEGER` |
| pit.metric_observation | `metric_code` | 指标代码 | 指标代码 | `VARCHAR(64)` |
| pit.metric_observation | `period_end` | 指标周期结束日 | 指标周期结束日 | `DATE` |
| pit.metric_observation | `event_at` | 事件时间 | 事件实际发生或指标对应的时间。 | `DATETIME` |
| pit.metric_observation | `source_published_at` | 来源发布时间 | 外部数据源声称该信息正式发布的时间。 | `DATETIME` |
| pit.metric_observation | `fetched_at` | 系统获取时间 | 系统实际成功取得该数据的时间，严格PIT回放以此判断数据是否可用。 | `DATETIME` |
| pit.metric_observation | `value_numeric` | 数值型取值 | 数值型取值 | `NUMERIC(24, 6)` |
| pit.metric_observation | `value_text` | 文本型取值 | 文本型取值 | `VARCHAR(512)` |
| pit.metric_observation | `value_json` | JSON取值 | JSON取值 | `JSON` |
| pit.metric_observation | `unit` | 单位 | 单位 | `VARCHAR(32)` |
| pit.metric_observation | `currency` | 货币 | 货币 | `VARCHAR(16)` |
| pit.metric_observation | `source_id` | 数据源ID | 数据来自哪个外部或内部数据源。 | `INTEGER` |
| pit.metric_observation | `raw_payload_id` | 原始载荷ID | 该清洗记录可追溯的原始响应元数据ID。 | `INTEGER` |
| pit.metric_observation | `data_hash` | 标准化数据哈希 | 标准化数据哈希 | `VARCHAR(64)` |
| pit.metric_observation | `quality_flags` | 数据质量标记 | 校验失败、异常跳变、映射失败、回补警告等信息。 | `JSON` |
| pit.metric_observation | `recorded_at` | 入库时间 | 数据写入本系统数据库的时间。 | `DATETIME` |
| pit.news_item_snapshot | `news_snapshot_id` | 新闻快照ID | 新闻快照ID | `INTEGER` |
| pit.news_item_snapshot | `security_id` | 证券内部ID | 系统内部稳定证券主键，不使用 ticker 作为外键。 | `INTEGER` |
| pit.news_item_snapshot | `news_type` | 新闻类型：stock_news/press_release | 新闻类型：stock_news/press_release | `VARCHAR(32)` |
| pit.news_item_snapshot | `title` | 标题 | 标题 | `VARCHAR(512)` |
| pit.news_item_snapshot | `url` | 原文URL | 原文URL | `TEXT` |
| pit.news_item_snapshot | `publisher` | 发布方 | 发布方 | `VARCHAR(128)` |
| pit.news_item_snapshot | `author` | 作者 | 作者 | `VARCHAR(128)` |
| pit.news_item_snapshot | `published_at` | 新闻发布时间 | 新闻发布时间 | `DATETIME` |
| pit.news_item_snapshot | `summary` | 正文摘要 | 正文摘要 | `TEXT` |
| pit.news_item_snapshot | `image_url` | 图片URL | 图片URL | `TEXT` |
| pit.news_item_snapshot | `sentiment_label` | 情绪标签 | 情绪标签 | `VARCHAR(32)` |
| pit.news_item_snapshot | `sentiment_score` | 情绪分数 | 情绪分数 | `NUMERIC(12, 6)` |
| pit.news_item_snapshot | `source_published_at` | 来源发布时间 | 外部数据源声称该信息正式发布的时间。 | `DATETIME` |
| pit.news_item_snapshot | `fetched_at` | 系统获取时间 | 系统实际成功取得该数据的时间，严格PIT回放以此判断数据是否可用。 | `DATETIME` |
| pit.news_item_snapshot | `source_id` | 数据源ID | 数据来自哪个外部或内部数据源。 | `INTEGER` |
| pit.news_item_snapshot | `raw_payload_id` | 原始载荷ID | 该清洗记录可追溯的原始响应元数据ID。 | `INTEGER` |
| pit.news_item_snapshot | `data_hash` | 标准化数据哈希 | 标准化数据哈希 | `VARCHAR(64)` |
| pit.news_item_snapshot | `quality_flags` | 数据质量标记 | 校验失败、异常跳变、映射失败、回补警告等信息。 | `JSON` |
| pit.news_item_snapshot | `recorded_at` | 入库时间 | 数据写入本系统数据库的时间。 | `DATETIME` |
| pit.sec_filing_snapshot | `sec_filing_id` | SEC文件快照ID | SEC文件快照ID | `INTEGER` |
| pit.sec_filing_snapshot | `security_id` | 证券内部ID | 系统内部稳定证券主键，不使用 ticker 作为外键。 | `INTEGER` |
| pit.sec_filing_snapshot | `form_type` | SEC表格类型，例如8-K、10-Q、10-K | SEC表格类型，例如8-K、10-Q、10-K | `VARCHAR(32)` |
| pit.sec_filing_snapshot | `filing_date` | 文件披露日期 | 文件披露日期 | `DATE` |
| pit.sec_filing_snapshot | `accepted_at` | SEC接受时间 | SEC接受时间 | `DATETIME` |
| pit.sec_filing_snapshot | `cik` | SEC CIK | SEC CIK | `VARCHAR(32)` |
| pit.sec_filing_snapshot | `filing_url` | SEC filing index链接 | SEC filing index链接 | `TEXT` |
| pit.sec_filing_snapshot | `final_url` | SEC最终文件链接 | SEC最终文件链接 | `TEXT` |
| pit.sec_filing_snapshot | `has_financials` | 是否包含财务数据 | 是否包含财务数据 | `BOOLEAN` |
| pit.sec_filing_snapshot | `source_published_at` | 来源发布时间 | 外部数据源声称该信息正式发布的时间。 | `DATETIME` |
| pit.sec_filing_snapshot | `fetched_at` | 系统获取时间 | 系统实际成功取得该数据的时间，严格PIT回放以此判断数据是否可用。 | `DATETIME` |
| pit.sec_filing_snapshot | `value_json` | 来源SEC文件行JSON | 来源SEC文件行JSON | `JSON` |
| pit.sec_filing_snapshot | `source_id` | 数据源ID | 数据来自哪个外部或内部数据源。 | `INTEGER` |
| pit.sec_filing_snapshot | `raw_payload_id` | 原始载荷ID | 该清洗记录可追溯的原始响应元数据ID。 | `INTEGER` |
| pit.sec_filing_snapshot | `data_hash` | 标准化数据哈希 | 标准化数据哈希 | `VARCHAR(64)` |
| pit.sec_filing_snapshot | `quality_flags` | 数据质量标记 | 校验失败、异常跳变、映射失败、回补警告等信息。 | `JSON` |
| pit.sec_filing_snapshot | `recorded_at` | 入库时间 | 数据写入本系统数据库的时间。 | `DATETIME` |
| pit.source_document_snapshot | `source_document_id` | 来源文档ID | 来源文档ID | `INTEGER` |
| pit.source_document_snapshot | `security_id` | 证券内部ID | 系统内部稳定证券主键，不使用 ticker 作为外键。 | `INTEGER` |
| pit.source_document_snapshot | `document_type` | 文档类型：press_release/sec_filing/earning_transcript等 | 文档类型：press_release/sec_filing/earning_transcript等 | `VARCHAR(64)` |
| pit.source_document_snapshot | `document_key` | 文档天然去重键 | 文档天然去重键 | `VARCHAR(512)` |
| pit.source_document_snapshot | `title` | 文档标题 | 文档标题 | `VARCHAR(512)` |
| pit.source_document_snapshot | `source_url` | 来源原文链接 | 来源原文链接 | `TEXT` |
| pit.source_document_snapshot | `source_event_at` | 文档对应事件时间 | 文档对应事件时间 | `DATETIME` |
| pit.source_document_snapshot | `source_published_at` | 来源发布时间 | 外部数据源声称该信息正式发布的时间。 | `DATETIME` |
| pit.source_document_snapshot | `fetched_at` | 系统获取时间 | 系统实际成功取得该数据的时间，严格PIT回放以此判断数据是否可用。 | `DATETIME` |
| pit.source_document_snapshot | `content_type` | 原文内容类型 | 原文内容类型 | `VARCHAR(64)` |
| pit.source_document_snapshot | `object_uri` | 原始文件路径 | gzip 压缩原始 JSON 的本地路径，未来可替换为 S3 或 MinIO URI。 | `TEXT` |
| pit.source_document_snapshot | `content_hash` | 原始内容哈希 | 原始响应内容的 SHA256，用于去重。 | `VARCHAR(64)` |
| pit.source_document_snapshot | `content_length` | 原文内容字节数 | 原文内容字节数 | `INTEGER` |
| pit.source_document_snapshot | `text_excerpt` | 原文文本预览 | 原文文本预览 | `TEXT` |
| pit.source_document_snapshot | `metadata_json` | 来源文档元数据 | 来源文档元数据 | `JSON` |
| pit.source_document_snapshot | `source_id` | 数据源ID | 数据来自哪个外部或内部数据源。 | `INTEGER` |
| pit.source_document_snapshot | `raw_payload_id` | 原始载荷ID | 该清洗记录可追溯的原始响应元数据ID。 | `INTEGER` |
| pit.source_document_snapshot | `data_hash` | 标准化数据哈希 | 标准化数据哈希 | `VARCHAR(64)` |
| pit.source_document_snapshot | `quality_flags` | 数据质量标记 | 校验失败、异常跳变、映射失败、回补警告等信息。 | `JSON` |
| pit.source_document_snapshot | `recorded_at` | 入库时间 | 数据写入本系统数据库的时间。 | `DATETIME` |
| raw.dataset_coverage | `coverage_id` | 覆盖状态ID | 覆盖状态ID | `INTEGER` |
| raw.dataset_coverage | `source_code` | 数据源代码 | 覆盖状态对应的数据源；当前批量 enrichment 固定为 fmp。 | `VARCHAR(64)` |
| raw.dataset_coverage | `dataset_code` | 数据集代码 | 覆盖状态对应的采集模块，例如 estimates、earnings、financials、news、sec_filings。 | `VARCHAR(64)` |
| raw.dataset_coverage | `symbol` | 股票代码 | 本次覆盖状态对应的 ticker。 | `VARCHAR(32)` |
| raw.dataset_coverage | `security_id` | 证券内部ID | 系统内部稳定证券主键，不使用 ticker 作为外键。 | `INTEGER` |
| raw.dataset_coverage | `status` | 覆盖状态 | ok 表示已有数据；no_data 表示接口确认空返回；unsupported 表示暂不支持；transient_failed 表示网络、限速或临时错误。 | `VARCHAR(32)` |
| raw.dataset_coverage | `last_checked_at` | 最近检查时间 | 系统最近一次检查该 ticker 在该数据集上是否有数据的时间。 | `DATETIME` |
| raw.dataset_coverage | `next_check_after` | 下次允许重试时间 | 断点续跑在这个时间之前会跳过该 ticker，避免无数据或暂时失败标的反复消耗请求。 | `DATETIME` |
| raw.dataset_coverage | `failure_count` | 连续失败次数 | 暂时失败的连续次数，用于退避重试；确认无数据时通常为 0。 | `INTEGER` |
| raw.dataset_coverage | `last_error` | 最近错误或原因 | 最近一次失败、空返回或跳过的简要原因。 | `TEXT` |
| raw.dataset_coverage | `metadata_json` | 覆盖状态元数据 | 记录最近一次更新该覆盖状态的 run_id、chunk 序号和运行状态。 | `JSON` |
| raw.dataset_coverage | `created_at` | 创建时间 | 创建时间 | `DATETIME` |
| raw.dataset_coverage | `updated_at` | 更新时间 | 更新时间 | `DATETIME` |
| raw.ingest_run | `run_id` | 采集运行ID | 采集运行ID | `INTEGER` |
| raw.ingest_run | `job_name` | 任务名称 | 任务名称 | `VARCHAR(128)` |
| raw.ingest_run | `dataset_code` | 数据集代码 | 数据集代码 | `VARCHAR(64)` |
| raw.ingest_run | `source_id` | 数据源ID | 数据来自哪个外部或内部数据源。 | `INTEGER` |
| raw.ingest_run | `collection_mode` | 采集模式 | live 为真实实时采集，backfill 为历史回补，replay 为重新解析原始数据。 | `VARCHAR(32)` |
| raw.ingest_run | `scheduled_at` | 计划执行时间 | 计划执行时间 | `DATETIME` |
| raw.ingest_run | `started_at` | 开始时间 | 开始时间 | `DATETIME` |
| raw.ingest_run | `finished_at` | 结束时间 | 结束时间 | `DATETIME` |
| raw.ingest_run | `status` | 任务状态 | 任务状态 | `VARCHAR(32)` |
| raw.ingest_run | `requested_count` | 请求数量 | 请求数量 | `INTEGER` |
| raw.ingest_run | `success_count` | 成功数量 | 成功数量 | `INTEGER` |
| raw.ingest_run | `failed_count` | 失败数量 | 失败数量 | `INTEGER` |
| raw.ingest_run | `skipped_count` | 跳过数量 | 跳过数量 | `INTEGER` |
| raw.ingest_run | `error_message` | 错误信息 | 错误信息 | `TEXT` |
| raw.ingest_run | `metadata_json` | 任务元数据 | 任务元数据 | `JSON` |
| raw.ingest_run | `created_at` | 创建时间 | 创建时间 | `DATETIME` |
| raw.payload | `payload_id` | 原始载荷ID | 原始载荷ID | `INTEGER` |
| raw.payload | `run_id` | 采集运行ID | 采集运行ID | `INTEGER` |
| raw.payload | `source_id` | 数据源ID | 数据来自哪个外部或内部数据源。 | `INTEGER` |
| raw.payload | `dataset_code` | 数据集代码 | 数据集代码 | `VARCHAR(64)` |
| raw.payload | `request_key` | 请求唯一键 | 请求唯一键 | `VARCHAR(255)` |
| raw.payload | `source_published_at` | 来源发布时间 | 外部数据源声称该信息正式发布的时间。 | `DATETIME` |
| raw.payload | `fetched_at` | 系统获取时间 | 系统实际成功取得该数据的时间，严格PIT回放以此判断数据是否可用。 | `DATETIME` |
| raw.payload | `content_hash` | 原始内容哈希 | 原始响应内容的 SHA256，用于去重。 | `VARCHAR(64)` |
| raw.payload | `object_uri` | 原始文件路径 | gzip 压缩原始 JSON 的本地路径，未来可替换为 S3 或 MinIO URI。 | `TEXT` |
| raw.payload | `content_type` | 内容类型 | 内容类型 | `VARCHAR(64)` |
| raw.payload | `compression` | 压缩方式 | 压缩方式 | `VARCHAR(16)` |
| raw.payload | `http_status` | HTTP状态码 | HTTP状态码 | `INTEGER` |
| raw.payload | `parser_version` | 解析器版本 | 解析器版本 | `VARCHAR(32)` |
| raw.payload | `schema_version` | 数据结构版本 | 数据结构版本 | `VARCHAR(32)` |
| raw.payload | `metadata_json` | 元数据 | 元数据 | `JSON` |
| raw.payload | `created_at` | 创建时间 | 创建时间 | `DATETIME` |
