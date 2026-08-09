# 交易工作台

一个本地优先的仓位管理、交易记录和交易日志系统。当前版本面向个人使用，数据存在本地 SQLite 文件里；代码结构保留了后续产品化需要的数据库层、领域计算层和 API 边界。

## 功能

- 账户设置：账户名、币种、初始资金
- 交易记录：股票、ETF、期权等买入/卖出流水；期权支持 CALL/PUT、到期日、行权价、合约乘数
- 自动日志：新增交易时自动创建关联日志草稿，交易和复盘天然绑定
- 仓位管理：由交易流水自动推导持仓、成本、市值、仓位占比
- 盈亏统计：现金、总权益、已实现盈亏、浮动盈亏、总盈亏、胜率、Profit Factor
- 价格标记：手动记录最新价格，用于估算持仓市值和浮动盈亏
- 资金流水：转入、转出、分红、利息、费用、税费、调整
- 交易日志：市场背景、交易假设、计划、复盘、错误、经验
- 数据导出：导出 JSON 快照

## 技术栈

- Next.js
- TypeScript
- SQLite
- Drizzle ORM
- better-sqlite3
- React

## 运行方式

进入项目目录：

```bash
cd /Users/aibao/invest/trading-app
```

首次运行先安装依赖并初始化数据库：

```bash
npm install
npm run db:init
```

启动开发服务器：

```bash
npm run dev -- --hostname 127.0.0.1 --port 3000
```

打开：

```text
http://127.0.0.1:3000
```

如果 `3000` 端口被占用，可以换端口：

```bash
npm run dev -- --hostname 127.0.0.1 --port 3001
```

## 生产模式

构建：

```bash
npm run build
```

启动：

```bash
npm run start
```

## 常用命令

```bash
npm run db:init     # 初始化 SQLite 表结构
npm run lint        # TypeScript 类型检查
npm run typecheck   # TypeScript 类型检查
npm run build       # 生产构建
```

## 数据位置

SQLite 数据库文件：

```text
trading-app/data/trading.sqlite
```

`data/*.sqlite`、`.next/`、`node_modules/` 都已经在 `.gitignore` 中，不会被提交。

## 目录结构

```text
trading-app/
  src/
    app/              Next.js 页面和 API 路由
    components/       前端工作台组件
    db/               SQLite/Drizzle schema 和初始化逻辑
    domain/           仓位、现金、盈亏等核心计算
    server/           数据读写 repository
  data/               本地 SQLite 数据文件
```

## 设计原则

系统以交易流水作为事实来源，持仓、现金、盈亏和统计都由流水自动推导。这样后续导入券商 CSV、增加多账户、接行情源或迁移到 Postgres 时，不需要重写核心计算逻辑。

新增交易时，系统会在同一个数据库事务里自动创建一篇关联日志。买入会生成进行中的交易计划草稿；卖出会生成退出复盘草稿，并尽量根据当前持仓成本推断盈利、亏损或打平。

期权交易里，“价格/权利金”按每股权利金填写，“数量”按合约数填写；系统会按 `合约数 × 权利金 × 合约乘数` 计算现金影响和持仓市值。美股标准期权默认合约乘数为 `100`。

## 后续方向

- 导入券商 CSV
- 按策略、标签、品种统计表现
- 增加风险控制：单笔风险、止损价、R 倍数、最大回撤
- 接入行情源自动更新价格
- 多账户和多用户支持
