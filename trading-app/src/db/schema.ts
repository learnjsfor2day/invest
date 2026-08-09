import { sql } from "drizzle-orm";
import { index, integer, real, sqliteTable, text, uniqueIndex } from "drizzle-orm/sqlite-core";

export const accounts = sqliteTable("accounts", {
  id: text("id").primaryKey(),
  name: text("name").notNull(),
  currency: text("currency").notNull().default("USD"),
  initialCashCents: integer("initial_cash_cents").notNull().default(0),
  createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
  updatedAt: text("updated_at").notNull().default(sql`CURRENT_TIMESTAMP`)
});

export const trades = sqliteTable(
  "trades",
  {
    id: text("id").primaryKey(),
    accountId: text("account_id")
      .notNull()
      .references(() => accounts.id, { onDelete: "cascade" }),
    tradeDate: text("trade_date").notNull(),
    symbol: text("symbol").notNull(),
    instrument: text("instrument").notNull().default("stock"),
    underlyingSymbol: text("underlying_symbol"),
    optionType: text("option_type", { enum: ["CALL", "PUT"] }),
    expirationDate: text("expiration_date"),
    strikeCents: integer("strike_cents"),
    contractMultiplier: integer("contract_multiplier").notNull().default(1),
    side: text("side", { enum: ["BUY", "SELL"] }).notNull(),
    quantity: real("quantity").notNull(),
    priceCents: integer("price_cents").notNull(),
    feesCents: integer("fees_cents").notNull().default(0),
    strategy: text("strategy"),
    setup: text("setup"),
    notes: text("notes"),
    tagsJson: text("tags_json").notNull().default("[]"),
    createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
    updatedAt: text("updated_at").notNull().default(sql`CURRENT_TIMESTAMP`)
  },
  (table) => ({
    accountSymbolIdx: index("trades_account_symbol_idx").on(table.accountId, table.symbol),
    tradeDateIdx: index("trades_trade_date_idx").on(table.tradeDate)
  })
);

export const cashFlows = sqliteTable(
  "cash_flows",
  {
    id: text("id").primaryKey(),
    accountId: text("account_id")
      .notNull()
      .references(() => accounts.id, { onDelete: "cascade" }),
    flowDate: text("flow_date").notNull(),
    type: text("type", {
      enum: ["DEPOSIT", "WITHDRAWAL", "DIVIDEND", "INTEREST", "FEE", "TAX", "ADJUSTMENT"]
    }).notNull(),
    amountCents: integer("amount_cents").notNull(),
    symbol: text("symbol"),
    notes: text("notes"),
    createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`)
  },
  (table) => ({
    accountDateIdx: index("cash_flows_account_date_idx").on(table.accountId, table.flowDate)
  })
);

export const journalEntries = sqliteTable(
  "journal_entries",
  {
    id: text("id").primaryKey(),
    accountId: text("account_id")
      .notNull()
      .references(() => accounts.id, { onDelete: "cascade" }),
    entryDate: text("entry_date").notNull(),
    title: text("title").notNull(),
    mood: text("mood"),
    strategy: text("strategy"),
    setup: text("setup"),
    timeframe: text("timeframe"),
    direction: text("direction"),
    result: text("result"),
    marketRegime: text("market_regime"),
    catalyst: text("catalyst"),
    confidence: integer("confidence"),
    plannedEntryCents: integer("planned_entry_cents"),
    plannedStopCents: integer("planned_stop_cents"),
    plannedTargetCents: integer("planned_target_cents"),
    plannedRiskCents: integer("planned_risk_cents"),
    plannedSize: real("planned_size"),
    actualEntryCents: integer("actual_entry_cents"),
    actualExitCents: integer("actual_exit_cents"),
    maxFavorableCents: integer("max_favorable_cents"),
    maxAdverseCents: integer("max_adverse_cents"),
    rMultiple: real("r_multiple"),
    executionScore: integer("execution_score"),
    disciplineScore: integer("discipline_score"),
    followedPlan: integer("followed_plan", { mode: "boolean" }),
    marketContext: text("market_context"),
    thesis: text("thesis"),
    plan: text("plan"),
    review: text("review"),
    mistakes: text("mistakes"),
    lessons: text("lessons"),
    symbolsJson: text("symbols_json").notNull().default("[]"),
    tagsJson: text("tags_json").notNull().default("[]"),
    createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
    updatedAt: text("updated_at").notNull().default(sql`CURRENT_TIMESTAMP`)
  },
  (table) => ({
    accountDateIdx: index("journal_entries_account_date_idx").on(table.accountId, table.entryDate)
  })
);

export const priceMarks = sqliteTable(
  "price_marks",
  {
    id: text("id").primaryKey(),
    accountId: text("account_id")
      .notNull()
      .references(() => accounts.id, { onDelete: "cascade" }),
    symbol: text("symbol").notNull(),
    markedAt: text("marked_at").notNull(),
    priceCents: integer("price_cents").notNull(),
    source: text("source").notNull().default("manual"),
    createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`)
  },
  (table) => ({
    accountSymbolMarkedIdx: uniqueIndex("price_marks_account_symbol_marked_idx").on(
      table.accountId,
      table.symbol,
      table.markedAt
    )
  })
);

export const journalTradeLinks = sqliteTable(
  "journal_trade_links",
  {
    id: text("id").primaryKey(),
    accountId: text("account_id")
      .notNull()
      .references(() => accounts.id, { onDelete: "cascade" }),
    journalId: text("journal_id")
      .notNull()
      .references(() => journalEntries.id, { onDelete: "cascade" }),
    tradeId: text("trade_id")
      .notNull()
      .references(() => trades.id, { onDelete: "cascade" }),
    createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`)
  },
  (table) => ({
    journalIdx: index("journal_trade_links_journal_idx").on(table.journalId),
    tradeIdx: index("journal_trade_links_trade_idx").on(table.tradeId),
    uniqueLinkIdx: uniqueIndex("journal_trade_links_unique_idx").on(table.journalId, table.tradeId)
  })
);

export type Account = typeof accounts.$inferSelect;
export type Trade = typeof trades.$inferSelect;
export type NewTrade = typeof trades.$inferInsert;
export type CashFlow = typeof cashFlows.$inferSelect;
export type NewCashFlow = typeof cashFlows.$inferInsert;
export type JournalEntry = typeof journalEntries.$inferSelect;
export type PriceMark = typeof priceMarks.$inferSelect;
export type JournalTradeLink = typeof journalTradeLinks.$inferSelect;
