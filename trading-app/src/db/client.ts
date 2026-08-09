import Database from "better-sqlite3";
import { drizzle } from "drizzle-orm/better-sqlite3";
import { mkdirSync } from "node:fs";
import path from "node:path";
import * as schema from "./schema";

const root = process.cwd();
const dataDir = path.join(root, "data");
const dbPath = process.env.TRADING_DB_PATH || path.join(dataDir, "trading.sqlite");

declare global {
  // eslint-disable-next-line no-var
  var tradingSqlite: Database.Database | undefined;
}

function createSqlite() {
  mkdirSync(dataDir, { recursive: true });
  const sqlite = new Database(dbPath);
  sqlite.pragma("journal_mode = WAL");
  sqlite.pragma("foreign_keys = ON");
  return sqlite;
}

export const sqlite = globalThis.tradingSqlite ?? createSqlite();

if (process.env.NODE_ENV !== "production") {
  globalThis.tradingSqlite = sqlite;
}

export const db = drizzle(sqlite, { schema });
export { dbPath };
