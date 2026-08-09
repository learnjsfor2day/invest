import { sqlite } from "./client";

const journalEntryColumns = [
  ["strategy", "TEXT"],
  ["setup", "TEXT"],
  ["timeframe", "TEXT"],
  ["direction", "TEXT"],
  ["result", "TEXT"],
  ["market_regime", "TEXT"],
  ["catalyst", "TEXT"],
  ["confidence", "INTEGER"],
  ["planned_entry_cents", "INTEGER"],
  ["planned_stop_cents", "INTEGER"],
  ["planned_target_cents", "INTEGER"],
  ["planned_risk_cents", "INTEGER"],
  ["planned_size", "REAL"],
  ["actual_entry_cents", "INTEGER"],
  ["actual_exit_cents", "INTEGER"],
  ["max_favorable_cents", "INTEGER"],
  ["max_adverse_cents", "INTEGER"],
  ["r_multiple", "REAL"],
  ["execution_score", "INTEGER"],
  ["discipline_score", "INTEGER"],
  ["followed_plan", "INTEGER"]
] as const;

const tradeColumns = [
  ["underlying_symbol", "TEXT"],
  ["option_type", "TEXT"],
  ["expiration_date", "TEXT"],
  ["strike_cents", "INTEGER"],
  ["contract_multiplier", "INTEGER DEFAULT 1"]
] as const;

function ensureColumns(table: string, columns: ReadonlyArray<readonly [string, string]>) {
  const existing = new Set(
    sqlite
      .prepare(`PRAGMA table_info(${table})`)
      .all()
      .map((row) => (row as { name: string }).name)
  );

  for (const [name, definition] of columns) {
    if (!existing.has(name)) {
      sqlite.exec(`ALTER TABLE ${table} ADD COLUMN ${name} ${definition}`);
    }
  }
}

export function ensureDatabase() {
  sqlite.exec(`
    PRAGMA foreign_keys = ON;

    CREATE TABLE IF NOT EXISTS accounts (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      currency TEXT NOT NULL DEFAULT 'USD',
      initial_cash_cents INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS trades (
      id TEXT PRIMARY KEY,
      account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
      trade_date TEXT NOT NULL,
      symbol TEXT NOT NULL,
      instrument TEXT NOT NULL DEFAULT 'stock',
      underlying_symbol TEXT,
      option_type TEXT,
      expiration_date TEXT,
      strike_cents INTEGER,
      contract_multiplier INTEGER NOT NULL DEFAULT 1,
      side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
      quantity REAL NOT NULL,
      price_cents INTEGER NOT NULL,
      fees_cents INTEGER NOT NULL DEFAULT 0,
      strategy TEXT,
      setup TEXT,
      notes TEXT,
      tags_json TEXT NOT NULL DEFAULT '[]',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS trades_account_symbol_idx
      ON trades(account_id, symbol);
    CREATE INDEX IF NOT EXISTS trades_trade_date_idx
      ON trades(trade_date);

    CREATE TABLE IF NOT EXISTS cash_flows (
      id TEXT PRIMARY KEY,
      account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
      flow_date TEXT NOT NULL,
      type TEXT NOT NULL CHECK (type IN ('DEPOSIT', 'WITHDRAWAL', 'DIVIDEND', 'INTEREST', 'FEE', 'TAX', 'ADJUSTMENT')),
      amount_cents INTEGER NOT NULL,
      symbol TEXT,
      notes TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS cash_flows_account_date_idx
      ON cash_flows(account_id, flow_date);

    CREATE TABLE IF NOT EXISTS journal_entries (
      id TEXT PRIMARY KEY,
      account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
      entry_date TEXT NOT NULL,
      title TEXT NOT NULL,
      mood TEXT,
      strategy TEXT,
      setup TEXT,
      timeframe TEXT,
      direction TEXT,
      result TEXT,
      market_regime TEXT,
      catalyst TEXT,
      confidence INTEGER,
      planned_entry_cents INTEGER,
      planned_stop_cents INTEGER,
      planned_target_cents INTEGER,
      planned_risk_cents INTEGER,
      planned_size REAL,
      actual_entry_cents INTEGER,
      actual_exit_cents INTEGER,
      max_favorable_cents INTEGER,
      max_adverse_cents INTEGER,
      r_multiple REAL,
      execution_score INTEGER,
      discipline_score INTEGER,
      followed_plan INTEGER,
      market_context TEXT,
      thesis TEXT,
      plan TEXT,
      review TEXT,
      mistakes TEXT,
      lessons TEXT,
      symbols_json TEXT NOT NULL DEFAULT '[]',
      tags_json TEXT NOT NULL DEFAULT '[]',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS journal_entries_account_date_idx
      ON journal_entries(account_id, entry_date);

    CREATE TABLE IF NOT EXISTS price_marks (
      id TEXT PRIMARY KEY,
      account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
      symbol TEXT NOT NULL,
      marked_at TEXT NOT NULL,
      price_cents INTEGER NOT NULL,
      source TEXT NOT NULL DEFAULT 'manual',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(account_id, symbol, marked_at)
    );

    CREATE TABLE IF NOT EXISTS journal_trade_links (
      id TEXT PRIMARY KEY,
      account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
      journal_id TEXT NOT NULL REFERENCES journal_entries(id) ON DELETE CASCADE,
      trade_id TEXT NOT NULL REFERENCES trades(id) ON DELETE CASCADE,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(journal_id, trade_id)
    );

    CREATE INDEX IF NOT EXISTS journal_trade_links_journal_idx
      ON journal_trade_links(journal_id);
    CREATE INDEX IF NOT EXISTS journal_trade_links_trade_idx
      ON journal_trade_links(trade_id);
  `);

  ensureColumns("trades", tradeColumns);
  ensureColumns("journal_entries", journalEntryColumns);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  ensureDatabase();
  console.log("trading database ready");
}
