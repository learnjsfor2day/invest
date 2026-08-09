import { and, desc, eq } from "drizzle-orm";
import { db } from "@/db/client";
import { ensureDatabase } from "@/db/init";
import { accounts, cashFlows, journalEntries, journalTradeLinks, priceMarks, trades } from "@/db/schema";
import type { NewCashFlow, NewTrade } from "@/db/schema";
import {
  getContractMultiplier,
  getTradeDisplaySymbol,
  getTradeGrossCents,
  getTradePositionKey,
  inferTradeDirection
} from "@/domain/instruments";
import { buildPortfolioSnapshot } from "@/domain/portfolio";

const defaultAccountId = "default";

type TradeInput = Omit<NewTrade, "id" | "accountId"> & {
  tradeDate: string;
  symbol: string;
  instrument: string;
  side: "BUY" | "SELL";
  quantity: number;
  priceCents: number;
  feesCents: number;
  tagsJson: string;
};

export async function getOrCreateDefaultAccount() {
  ensureDatabase();
  const existing = await db.query.accounts.findFirst({
    where: eq(accounts.id, defaultAccountId)
  });
  if (existing) return existing;

  const now = new Date().toISOString();
  const account = {
    id: defaultAccountId,
    name: "主账户",
    currency: "USD",
    initialCashCents: 10000000,
    createdAt: now,
    updatedAt: now
  };
  await db.insert(accounts).values(account);
  return account;
}

export async function updateDefaultAccount(input: {
  name: string;
  currency: string;
  initialCashCents: number;
}) {
  const account = await getOrCreateDefaultAccount();
  const now = new Date().toISOString();
  await db
    .update(accounts)
    .set({
      name: input.name,
      currency: input.currency,
      initialCashCents: input.initialCashCents,
      updatedAt: now
    })
    .where(eq(accounts.id, account.id));
}

export async function getSnapshot() {
  const account = await getOrCreateDefaultAccount();
  const [tradeRows, cashFlowRows, journalRows, priceRows, linkRows] = await Promise.all([
    db.query.trades.findMany({
      where: eq(trades.accountId, account.id)
    }),
    db.query.cashFlows.findMany({
      where: eq(cashFlows.accountId, account.id)
    }),
    db.query.journalEntries.findMany({
      where: eq(journalEntries.accountId, account.id),
      orderBy: [desc(journalEntries.entryDate), desc(journalEntries.createdAt)],
      limit: 100
    }),
    db.query.priceMarks.findMany({
      where: eq(priceMarks.accountId, account.id)
    }),
    db.query.journalTradeLinks.findMany({
      where: eq(journalTradeLinks.accountId, account.id)
    })
  ]);

  return buildPortfolioSnapshot({
    account,
    trades: tradeRows,
    cashFlows: cashFlowRows,
    journals: journalRows,
    priceMarks: priceRows,
    journalTradeLinks: linkRows
  });
}

function estimateOpenPosition(rows: TradeInput[]) {
  const sorted = [...rows].sort((a, b) => String(a.tradeDate).localeCompare(String(b.tradeDate)));
  let quantity = 0;
  let costBasisCents = 0;

  for (const row of sorted) {
    const rowQuantity = Number(row.quantity);
    const grossCents = getTradeGrossCents(row);
    const feesCents = Number(row.feesCents ?? 0);

    if (row.side === "BUY") {
      quantity += rowQuantity;
      costBasisCents += grossCents + feesCents;
    } else if (quantity > 0) {
      const avgCost = costBasisCents / quantity;
      const closedCost = Math.round(avgCost * rowQuantity);
      quantity -= rowQuantity;
      costBasisCents -= closedCost;
      if (Math.abs(quantity) < 0.000001) {
        quantity = 0;
        costBasisCents = 0;
      }
    }
  }

  return { quantity, costBasisCents };
}

function inferSellResult(input: TradeInput, priorTrades: TradeInput[]) {
  if (input.side !== "SELL") return null;
  const positionKey = getTradePositionKey(input);
  const position = estimateOpenPosition(priorTrades.filter((trade) => getTradePositionKey(trade) === positionKey));
  if (position.quantity <= 0) return null;

  const avgCost = position.costBasisCents / position.quantity;
  const grossCents = getTradeGrossCents(input);
  const closedCost = Math.round(avgCost * Number(input.quantity));
  const realizedCents = grossCents - Number(input.feesCents ?? 0) - closedCost;

  if (Math.abs(realizedCents) <= 1) return "BREAKEVEN";
  return realizedCents > 0 ? "WIN" : "LOSS";
}

export async function addTrade(input: TradeInput) {
  const account = await getOrCreateDefaultAccount();
  const now = new Date().toISOString();
  const tradeId = crypto.randomUUID();
  const journalId = crypto.randomUUID();
  const symbol = String(input.symbol).toUpperCase();
  const normalizedInput = {
    ...input,
    symbol,
    underlyingSymbol: input.instrument === "option" ? (input.underlyingSymbol || symbol).toUpperCase() : null,
    optionType: input.instrument === "option" ? input.optionType ?? "CALL" : null,
    expirationDate: input.instrument === "option" ? input.expirationDate ?? null : null,
    strikeCents: input.instrument === "option" ? input.strikeCents ?? null : null,
    contractMultiplier: getContractMultiplier(input)
  } satisfies TradeInput;
  const displaySymbol = getTradeDisplaySymbol(normalizedInput);
  const sideLabel = input.side === "BUY" ? "买入" : "卖出";

  db.transaction((tx) => {
    const priorSymbolTrades = tx.query.trades.findMany({
      where: and(eq(trades.accountId, account.id), eq(trades.symbol, symbol))
    }).sync();
    const sellResult = inferSellResult(normalizedInput, priorSymbolTrades as TradeInput[]);

    tx.insert(trades).values({
      ...normalizedInput,
      id: tradeId,
      accountId: account.id,
      createdAt: now,
      updatedAt: now
    }).run();

    tx.insert(journalEntries).values({
      id: journalId,
      accountId: account.id,
      entryDate: String(normalizedInput.tradeDate),
      title: `${displaySymbol} ${sideLabel}`,
      mood: null,
      strategy: normalizedInput.strategy ?? null,
      setup: normalizedInput.setup ?? null,
      timeframe: null,
      direction: inferTradeDirection(normalizedInput),
      result: normalizedInput.side === "BUY" ? "OPEN" : sellResult,
      marketRegime: null,
      catalyst: null,
      confidence: null,
      plannedEntryCents: normalizedInput.side === "BUY" ? Number(normalizedInput.priceCents) : null,
      plannedStopCents: null,
      plannedTargetCents: null,
      plannedRiskCents: null,
      plannedSize: Number(normalizedInput.quantity),
      actualEntryCents: normalizedInput.side === "BUY" ? Number(normalizedInput.priceCents) : null,
      actualExitCents: normalizedInput.side === "SELL" ? Number(normalizedInput.priceCents) : null,
      maxFavorableCents: null,
      maxAdverseCents: null,
      rMultiple: null,
      executionScore: null,
      disciplineScore: null,
      followedPlan: null,
      marketContext: null,
      thesis: normalizedInput.side === "BUY" ? normalizedInput.notes ?? null : null,
      plan: null,
      review: normalizedInput.side === "SELL" ? normalizedInput.notes ?? null : null,
      mistakes: null,
      lessons: null,
      symbolsJson: JSON.stringify(displaySymbol === symbol ? [symbol] : [symbol, displaySymbol]),
      tagsJson: normalizedInput.tagsJson ?? "[]",
      createdAt: now,
      updatedAt: now
    }).run();

    tx.insert(journalTradeLinks).values({
      id: crypto.randomUUID(),
      accountId: account.id,
      journalId,
      tradeId,
      createdAt: now
    }).run();
  });
}

export async function deleteTrade(id: string) {
  const account = await getOrCreateDefaultAccount();
  await db.delete(trades).where(and(eq(trades.id, id), eq(trades.accountId, account.id)));
}

export async function addCashFlow(input: Omit<NewCashFlow, "id" | "accountId">) {
  const account = await getOrCreateDefaultAccount();
  await db.insert(cashFlows).values({
    ...input,
    id: crypto.randomUUID(),
    accountId: account.id
  });
}

export async function deleteCashFlow(id: string) {
  const account = await getOrCreateDefaultAccount();
  await db.delete(cashFlows).where(and(eq(cashFlows.id, id), eq(cashFlows.accountId, account.id)));
}

export async function addPriceMark(input: {
  symbol: string;
  markedAt: string;
  priceCents: number;
  source?: string;
}) {
  const account = await getOrCreateDefaultAccount();
  await db
    .insert(priceMarks)
    .values({
      id: crypto.randomUUID(),
      accountId: account.id,
      symbol: input.symbol,
      markedAt: input.markedAt,
      priceCents: input.priceCents,
      source: input.source ?? "manual"
    })
    .onConflictDoUpdate({
      target: [priceMarks.accountId, priceMarks.symbol, priceMarks.markedAt],
      set: {
        priceCents: input.priceCents,
        source: input.source ?? "manual"
      }
    });
}

export async function addJournalEntry(input: {
  entryDate: string;
  title: string;
  mood?: string | null;
  strategy?: string | null;
  setup?: string | null;
  timeframe?: string | null;
  direction?: string | null;
  result?: string | null;
  marketRegime?: string | null;
  catalyst?: string | null;
  confidence?: number | null;
  plannedEntryCents?: number | null;
  plannedStopCents?: number | null;
  plannedTargetCents?: number | null;
  plannedRiskCents?: number | null;
  plannedSize?: number | null;
  actualEntryCents?: number | null;
  actualExitCents?: number | null;
  maxFavorableCents?: number | null;
  maxAdverseCents?: number | null;
  rMultiple?: number | null;
  executionScore?: number | null;
  disciplineScore?: number | null;
  followedPlan?: boolean | null;
  marketContext?: string | null;
  thesis?: string | null;
  plan?: string | null;
  review?: string | null;
  mistakes?: string | null;
  lessons?: string | null;
  symbolsJson: string;
  tagsJson: string;
  linkedTradeIds?: string[];
}) {
  const account = await getOrCreateDefaultAccount();
  const now = new Date().toISOString();
  const { linkedTradeIds = [], ...journalInput } = input;
  const journalId = crypto.randomUUID();
  const distinctTradeIds = [...new Set(linkedTradeIds.filter(Boolean))];

  db.transaction((tx) => {
    tx.insert(journalEntries).values({
      id: journalId,
      accountId: account.id,
      ...journalInput,
      createdAt: now,
      updatedAt: now
    }).run();

    if (!distinctTradeIds.length) return;

    const validTrades = tx.query.trades.findMany({
      where: eq(trades.accountId, account.id)
    }).sync();
    const validTradeIds = new Set(validTrades.map((trade) => trade.id));
    const links = distinctTradeIds
      .filter((tradeId) => validTradeIds.has(tradeId))
      .map((tradeId) => ({
        id: crypto.randomUUID(),
        accountId: account.id,
        journalId,
        tradeId,
        createdAt: now
      }));

    if (links.length) {
      tx.insert(journalTradeLinks).values(links).onConflictDoNothing().run();
    }
  });
}

export async function deleteJournalEntry(id: string) {
  const account = await getOrCreateDefaultAccount();
  await db.delete(journalEntries).where(and(eq(journalEntries.id, id), eq(journalEntries.accountId, account.id)));
}
