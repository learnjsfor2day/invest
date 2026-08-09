FIELD_LABELS_ZH = {
    "security_id": {
        "name": "证券内部ID",
        "description": "系统内部稳定证券主键，不使用 ticker 作为外键。",
    },
    "primary_ticker": {
        "name": "主要代码",
        "description": "当前用于展示的主要 ticker，历史回放应使用 security_identifier 判断当时有效代码。",
    },
    "identifier_type": {
        "name": "标识符类型",
        "description": "ticker、cik、figi、cusip、isin 或 vendor_symbol。",
    },
    "identifier_value": {
        "name": "标识符取值",
        "description": "具体的 ticker、CIK 或供应商代码。",
    },
    "valid_from": {
        "name": "生效时间",
        "description": "该标识符开始有效的时间。",
    },
    "valid_to": {
        "name": "失效时间",
        "description": "该标识符失效的时间；为空表示当前仍有效。",
    },
    "source_id": {
        "name": "数据源ID",
        "description": "数据来自哪个外部或内部数据源。",
    },
    "collection_mode": {
        "name": "采集模式",
        "description": "live 为真实实时采集，backfill 为历史回补，replay 为重新解析原始数据。",
    },
    "event_at": {
        "name": "事件时间",
        "description": "事件实际发生或指标对应的时间。",
    },
    "source_published_at": {
        "name": "来源发布时间",
        "description": "外部数据源声称该信息正式发布的时间。",
    },
    "fetched_at": {
        "name": "系统获取时间",
        "description": "系统实际成功取得该数据的时间，严格PIT回放以此判断数据是否可用。",
    },
    "recorded_at": {
        "name": "入库时间",
        "description": "数据写入本系统数据库的时间。",
    },
    "snapshot_at": {
        "name": "快照时间",
        "description": "该条快照代表的业务观察时间，通常等于系统获取时间。",
    },
    "fiscal_period_end": {
        "name": "财报周期结束日",
        "description": "财务预测或财报事件对应的明确周期结束日期。",
    },
    "period_type": {
        "name": "周期类型",
        "description": "quarter 表示季度，fiscal_year 表示财年。",
    },
    "eps_mean": {
        "name": "EPS预期均值",
        "description": "分析师每股收益预期的平均值。",
    },
    "eps_high": {
        "name": "EPS预期最高值",
        "description": "分析师每股收益预期的最高值。",
    },
    "eps_low": {
        "name": "EPS预期最低值",
        "description": "分析师每股收益预期的最低值。",
    },
    "revenue_mean": {
        "name": "营收预期均值",
        "description": "分析师营收预期平均值。",
    },
    "revenue_high": {
        "name": "营收预期最高值",
        "description": "分析师营收预期最高值。",
    },
    "revenue_low": {
        "name": "营收预期最低值",
        "description": "分析师营收预期最低值。",
    },
    "target_mean": {
        "name": "目标价均值",
        "description": "分析师目标价的均值或一致预期。",
    },
    "target_high": {
        "name": "目标价最高值",
        "description": "分析师目标价最高值。",
    },
    "target_low": {
        "name": "目标价最低值",
        "description": "分析师目标价最低值。",
    },
    "strong_buy_count": {
        "name": "强烈买入数量",
        "description": "评级分布中的强烈买入数量。",
    },
    "buy_count": {
        "name": "买入数量",
        "description": "评级分布中的买入数量。",
    },
    "hold_count": {
        "name": "持有数量",
        "description": "评级分布中的持有数量。",
    },
    "sell_count": {
        "name": "卖出数量",
        "description": "评级分布中的卖出数量。",
    },
    "strong_sell_count": {
        "name": "强烈卖出数量",
        "description": "评级分布中的强烈卖出数量。",
    },
    "expected_report_date": {
        "name": "预计财报日",
        "description": "当时已知的预计财报披露日期。",
    },
    "expected_report_session": {
        "name": "预计披露时段",
        "description": "before_open 盘前，after_close 盘后，during_market 盘中，unknown 未知。",
    },
    "estimated_eps": {
        "name": "预计EPS",
        "description": "财报日历中提供的预计每股收益。",
    },
    "estimated_revenue": {
        "name": "预计营收",
        "description": "财报日历中提供的预计营收。",
    },
    "trade_date": {
        "name": "交易日期",
        "description": "美股交易日期。",
    },
    "adjusted_close": {
        "name": "复权收盘价",
        "description": "数据源返回的复权收盘价。",
    },
    "revision_no": {
        "name": "修订版本号",
        "description": "同一证券同一交易日的日线数据版本号，修订时追加新版本。",
    },
    "quality_flags": {
        "name": "数据质量标记",
        "description": "校验失败、异常跳变、映射失败、回补警告等信息。",
    },
    "raw_payload_id": {
        "name": "原始载荷ID",
        "description": "该清洗记录可追溯的原始响应元数据ID。",
    },
    "content_hash": {
        "name": "原始内容哈希",
        "description": "原始响应内容的 SHA256，用于去重。",
    },
    "object_uri": {
        "name": "原始文件路径",
        "description": "gzip 压缩原始 JSON 的本地路径，未来可替换为 S3 或 MinIO URI。",
    },
    "pit.macro_event_snapshot.id": {
        "name": "宏观事件快照ID",
        "description": "宏观事件每个可见版本的内部主键；同一事件发生修订时会生成新的快照ID。",
    },
    "pit.macro_event_snapshot.source": {
        "name": "数据源",
        "description": "宏观事件来自哪个供应商；当前固定为 FMP。",
    },
    "pit.macro_event_snapshot.provider_event_id": {
        "name": "供应商事件ID",
        "description": "FMP 原始事件ID；如果接口提供稳定ID，会优先用于生成事件稳定键。",
    },
    "pit.macro_event_snapshot.event_key": {
        "name": "事件稳定键",
        "description": "用于识别同一个宏观事件的稳定唯一键，不包含本系统观察时间；同一事件修订时仍应尽量保持一致。",
    },
    "pit.macro_event_snapshot.event_name": {
        "name": "英文事件名称",
        "description": "FMP 返回的英文宏观事件名称，例如 CPI YoY、Core CPI MoM 或 Fed Speech。",
    },
    "pit.macro_event_snapshot.event_name_cn": {
        "name": "中文事件名称",
        "description": "事件中文别名；第一版允许为空，后续可通过本地事件名称映射表补齐。",
    },
    "pit.macro_event_snapshot.country": {
        "name": "国家/地区",
        "description": "宏观事件所属国家或地区；美股雷达主要关注 US。",
    },
    "pit.macro_event_snapshot.currency": {
        "name": "货币代码",
        "description": "事件关联货币，例如 USD；用于区分同名跨市场宏观事件。",
    },
    "pit.macro_event_snapshot.release_at_utc": {
        "name": "公布时间UTC",
        "description": "FMP 当时给出的计划或实际公布时间，统一转为 UTC；公布时间调整会作为新版本快照保留。",
    },
    "pit.macro_event_snapshot.impact": {
        "name": "重要程度",
        "description": "FMP 对宏观事件的影响等级，例如 High、Medium、Low；用于交易前过滤高影响事件。",
    },
    "pit.macro_event_snapshot.actual_raw": {
        "name": "实际值原文",
        "description": "数据公布后的实际值原始文本，保留百分号、K/M/B 等来源格式，便于追溯和展示。",
    },
    "pit.macro_event_snapshot.estimate_raw": {
        "name": "预期值原文",
        "description": "市场一致预期或预测值原始文本，用于计算宏观数据是否超预期。",
    },
    "pit.macro_event_snapshot.previous_raw": {
        "name": "前值原文",
        "description": "上一期公布值或修正后前值的原始文本；前值修订会产生新的 payload_hash。",
    },
    "pit.macro_event_snapshot.actual_value": {
        "name": "实际值数值",
        "description": "从实际值原文中解析出的数值，便于排序、计算预期差和后续回测。",
    },
    "pit.macro_event_snapshot.estimate_value": {
        "name": "预期值数值",
        "description": "从预期值原文中解析出的数值；百分比按显示数值保存，例如 3.5% 保存为 3.5。",
    },
    "pit.macro_event_snapshot.previous_value": {
        "name": "前值数值",
        "description": "从前值原文中解析出的数值；无法解析时保留为空但 raw 字段仍保存。",
    },
    "pit.macro_event_snapshot.unit": {
        "name": "单位",
        "description": "解析出的单位或数量级，例如 %、K、M、B；用于展示和预期差解释。",
    },
    "pit.macro_event_snapshot.observed_at_utc": {
        "name": "系统观察时间UTC",
        "description": "本系统实际获取到这一版宏观事件数据的时间；严格 PIT 回测以此判断当时是否已知。",
    },
    "pit.macro_event_snapshot.is_backfill": {
        "name": "是否历史回填",
        "description": "标记该快照是否由 backfill 模式写入；严格 PIT 回测默认只使用 live 快照。",
    },
    "pit.macro_event_snapshot.payload_hash": {
        "name": "原始载荷哈希",
        "description": "规范化后的单条宏观事件 JSON 的 SHA256；与 event_key 组成唯一约束，避免完全重复入库。",
    },
    "pit.macro_event_snapshot.raw_json": {
        "name": "FMP原始JSON",
        "description": "FMP 返回的完整宏观事件原始字段；任何原始字段变化都会形成新的 payload_hash。",
    },
    "pit.macro_event_snapshot.source_id": {
        "name": "数据源ID",
        "description": "内部数据源表主键，用于把宏观事件快照追溯到 FMP 数据源配置。",
    },
    "pit.macro_event_snapshot.raw_payload_id": {
        "name": "原始载荷ID",
        "description": "对应 raw.payload 的原始响应ID，可回看当次 FMP 请求窗口和 gzip 原始文件。",
    },
    "pit.macro_event_snapshot.created_at": {
        "name": "入库时间",
        "description": "该宏观事件快照写入本地数据库的时间。",
    },
    "pit.financial_fact_snapshot.value_json": {
        "name": "财务核心字段JSON",
        "description": "用于筛选和展示的轻量财务字段；FMP完整原始响应保存在 raw.payload 指向的 gzip 文件中。",
    },
    "raw.dataset_coverage.source_code": {
        "name": "数据源代码",
        "description": "覆盖状态对应的数据源；当前批量 enrichment 固定为 fmp。",
    },
    "raw.dataset_coverage.dataset_code": {
        "name": "数据集代码",
        "description": "覆盖状态对应的采集模块，例如 estimates、earnings、financials、news、sec_filings。",
    },
    "raw.dataset_coverage.symbol": {
        "name": "股票代码",
        "description": "本次覆盖状态对应的 ticker。",
    },
    "raw.dataset_coverage.status": {
        "name": "覆盖状态",
        "description": "ok 表示已有数据；no_data 表示接口确认空返回；unsupported 表示暂不支持；transient_failed 表示网络、限速或临时错误。",
    },
    "raw.dataset_coverage.last_checked_at": {
        "name": "最近检查时间",
        "description": "系统最近一次检查该 ticker 在该数据集上是否有数据的时间。",
    },
    "raw.dataset_coverage.next_check_after": {
        "name": "下次允许重试时间",
        "description": "断点续跑在这个时间之前会跳过该 ticker，避免无数据或暂时失败标的反复消耗请求。",
    },
    "raw.dataset_coverage.failure_count": {
        "name": "连续失败次数",
        "description": "暂时失败的连续次数，用于退避重试；确认无数据时通常为 0。",
    },
    "raw.dataset_coverage.last_error": {
        "name": "最近错误或原因",
        "description": "最近一次失败、空返回或跳过的简要原因。",
    },
    "raw.dataset_coverage.metadata_json": {
        "name": "覆盖状态元数据",
        "description": "记录最近一次更新该覆盖状态的 run_id、chunk 序号和运行状态。",
    },
}

ENUM_LABELS_ZH = {
    "live": "实时采集",
    "backfill": "历史回补",
    "replay": "重新解析",
    "before_open": "盘前",
    "after_close": "盘后",
    "during_market": "盘中",
    "unknown": "未知",
    "success": "成功",
    "partial_success": "部分成功",
    "failed": "失败",
    "running": "运行中",
    "pending": "等待中",
}
