import type { Account, CashFlow, JournalEntry, JournalTradeLink, PriceMark, Trade } from "@/db/schema";
import {
  getContractMultiplier,
  getTradeDisplaySymbol,
  getTradeGrossCents,
  getTradePositionKey
} from "./instruments";
import { parseJsonList } from "./tags";

export type Position = {
  positionKey: string;
  symbol: string;
  instrument: string;
  underlyingSymbol: string | null;
  optionType: string | null;
  expirationDate: string | null;
  strikeCents: number | null;
  contractMultiplier: number;
  quantity: number;
  avgCostCents: number;
  costBasisCents: number;
  lastPriceCents: number;
  lastMarkedAt: string | null;
  marketValueCents: number;
  unrealizedPnlCents: number;
  realizedPnlCents: number;
  allocation: number;
};

export type RealizedEvent = {
  tradeId: string;
  tradeDate: string;
  symbol: string;
  pnlCents: number;
};

export type TradeView = Trade & {
  tags: string[];
  grossCents: number;
  cashImpactCents: number;
  journalCount: number;
};

export type CashFlowView = CashFlow;

export type JournalView = JournalEntry & {
  symbols: string[];
  tags: string[];
  linkedTrades: LinkedTradeView[];
};

export type LinkedTradeView = {
  id: string;
  tradeDate: string;
  symbol: string;
  side: "BUY" | "SELL";
  quantity: number;
  priceCents: number;
  strategy: string | null;
  setup: string | null;
};

export type PortfolioSnapshot = {
  account: Account;
  positions: Position[];
  trades: TradeView[];
  cashFlows: CashFlowView[];
  journals: JournalView[];
  totals: {
    cashCents: number;
    positionValueCents: number;
    equityCents: number;
    costBasisCents: number;
    realizedPnlCents: number;
    unrealizedPnlCents: number;
    totalPnlCents: number;
    exposurePct: number;
    winRate: number;
    profitFactor: number | null;
    avgWinCents: number;
    avgLossCents: number;
    largestLossCents: number;
    tradeCount: number;
    openPositionCount: number;
  };
};

type WorkingPosition = {
  positionKey: string;
  symbol: string;
  instrument: string;
  underlyingSymbol: string | null;
  optionType: string | null;
  expirationDate: string | null;
  strikeCents: number | null;
  contractMultiplier: number;
  quantity: number;
  costBasisCents: number;
  realizedPnlCents: number;
};

function latestMarksBySymbol(priceMarks: PriceMark[]) {
  const marks = new Map<string, PriceMark>();
  for (const mark of priceMarks) {
    const symbol = mark.symbol.toUpperCase();
    const current = marks.get(symbol);
    if (!current || mark.markedAt > current.markedAt || mark.createdAt > current.createdAt) {
      marks.set(symbol, mark);
    }
  }
  return marks;
}

function signedCashFlow(flow: CashFlow) {
  if (flow.type === "WITHDRAWAL" || flow.type === "FEE" || flow.type === "TAX") {
    return -Math.abs(flow.amountCents);
  }
  return flow.amountCents;
}

export function buildPortfolioSnapshot(input: {
  account: Account;
  trades: Trade[];
  cashFlows: CashFlow[];
  journals: JournalEntry[];
  priceMarks: PriceMark[];
  journalTradeLinks: JournalTradeLink[];
}): PortfolioSnapshot {
  const sortedTrades = [...input.trades].sort((a, b) => {
    const date = a.tradeDate.localeCompare(b.tradeDate);
    if (date !== 0) return date;
    return a.createdAt.localeCompare(b.createdAt);
  });

  const working = new Map<string, WorkingPosition>();
  const realizedEvents: RealizedEvent[] = [];
  let tradeCashImpactCents = 0;

  const journalCountByTrade = new Map<string, number>();
  const tradeIdsByJournal = new Map<string, string[]>();
  for (const link of input.journalTradeLinks) {
    journalCountByTrade.set(link.tradeId, (journalCountByTrade.get(link.tradeId) ?? 0) + 1);
    const ids = tradeIdsByJournal.get(link.journalId) ?? [];
    ids.push(link.tradeId);
    tradeIdsByJournal.set(link.journalId, ids);
  }

  const tradeById = new Map(input.trades.map((trade) => [trade.id, trade]));

  const tradeViews: TradeView[] = sortedTrades.map((trade) => {
    const symbol = getTradeDisplaySymbol(trade);
    const positionKey = getTradePositionKey(trade);
    const contractMultiplier = getContractMultiplier(trade);
    const grossCents = getTradeGrossCents(trade);
    const cashImpactCents =
      trade.side === "BUY" ? -(grossCents + trade.feesCents) : grossCents - trade.feesCents;
    tradeCashImpactCents += cashImpactCents;

    const position =
      working.get(positionKey) ??
      ({
        positionKey,
        symbol,
        instrument: trade.instrument,
        underlyingSymbol: trade.underlyingSymbol,
        optionType: trade.optionType,
        expirationDate: trade.expirationDate,
        strikeCents: trade.strikeCents,
        contractMultiplier,
        quantity: 0,
        costBasisCents: 0,
        realizedPnlCents: 0
      } satisfies WorkingPosition);

    if (trade.side === "BUY") {
      position.quantity += trade.quantity;
      position.costBasisCents += grossCents + trade.feesCents;
      position.instrument = trade.instrument;
      position.symbol = symbol;
      position.underlyingSymbol = trade.underlyingSymbol;
      position.optionType = trade.optionType;
      position.expirationDate = trade.expirationDate;
      position.strikeCents = trade.strikeCents;
      position.contractMultiplier = contractMultiplier;
    } else {
      const avgCost = position.quantity > 0 ? position.costBasisCents / position.quantity : 0;
      const closedCost = Math.round(avgCost * trade.quantity);
      const realizedPnlCents = grossCents - trade.feesCents - closedCost;
      position.quantity -= trade.quantity;
      position.costBasisCents -= closedCost;
      position.realizedPnlCents += realizedPnlCents;
      realizedEvents.push({
        tradeId: trade.id,
        tradeDate: trade.tradeDate,
        symbol,
        pnlCents: realizedPnlCents
      });

      if (Math.abs(position.quantity) < 0.000001) {
        position.quantity = 0;
        position.costBasisCents = 0;
      }
    }

    working.set(positionKey, position);

    return {
      ...trade,
      symbol,
      tags: parseJsonList(trade.tagsJson),
      grossCents,
      cashImpactCents,
      journalCount: journalCountByTrade.get(trade.id) ?? 0
    };
  });

  const latestMarks = latestMarksBySymbol(input.priceMarks);
  const cashFlowCents = input.cashFlows.reduce((total, flow) => total + signedCashFlow(flow), 0);
  const cashCents = input.account.initialCashCents + cashFlowCents + tradeCashImpactCents;

  let positionValueCents = 0;
  let costBasisCents = 0;
  let realizedPnlCents = 0;

  const positions: Position[] = Array.from(working.values())
    .filter((position) => Math.abs(position.quantity) > 0.000001)
    .map((position) => {
      const mark = latestMarks.get(position.symbol);
      const avgCostCents = position.quantity
        ? Math.round(position.costBasisCents / (position.quantity * position.contractMultiplier))
        : 0;
      const lastPriceCents = mark?.priceCents ?? avgCostCents;
      const marketValueCents = Math.round(position.quantity * lastPriceCents * position.contractMultiplier);
      const unrealizedPnlCents = marketValueCents - position.costBasisCents;
      positionValueCents += marketValueCents;
      costBasisCents += position.costBasisCents;
      realizedPnlCents += position.realizedPnlCents;

      return {
        positionKey: position.positionKey,
        symbol: position.symbol,
        instrument: position.instrument,
        underlyingSymbol: position.underlyingSymbol,
        optionType: position.optionType,
        expirationDate: position.expirationDate,
        strikeCents: position.strikeCents,
        contractMultiplier: position.contractMultiplier,
        quantity: position.quantity,
        avgCostCents,
        costBasisCents: position.costBasisCents,
        lastPriceCents,
        lastMarkedAt: mark?.markedAt ?? null,
        marketValueCents,
        unrealizedPnlCents,
        realizedPnlCents: position.realizedPnlCents,
        allocation: 0
      };
    })
    .sort((a, b) => b.marketValueCents - a.marketValueCents);

  for (const position of positions) {
    position.allocation = positionValueCents ? position.marketValueCents / positionValueCents : 0;
  }

  for (const position of working.values()) {
    if (Math.abs(position.quantity) <= 0.000001) {
      realizedPnlCents += position.realizedPnlCents;
    }
  }

  const equityCents = cashCents + positionValueCents;
  const unrealizedPnlCents = positions.reduce((total, item) => total + item.unrealizedPnlCents, 0);
  const wins = realizedEvents.filter((event) => event.pnlCents > 0);
  const losses = realizedEvents.filter((event) => event.pnlCents < 0);
  const grossWinCents = wins.reduce((total, event) => total + event.pnlCents, 0);
  const grossLossCents = Math.abs(losses.reduce((total, event) => total + event.pnlCents, 0));
  const avgWinCents = wins.length ? Math.round(grossWinCents / wins.length) : 0;
  const avgLossCents = losses.length ? Math.round(-grossLossCents / losses.length) : 0;
  const largestLossCents = losses.length ? Math.min(...losses.map((event) => event.pnlCents)) : 0;

  return {
    account: input.account,
    positions,
    trades: [...tradeViews].reverse(),
    cashFlows: [...input.cashFlows].sort((a, b) => b.flowDate.localeCompare(a.flowDate)),
    journals: [...input.journals]
      .sort((a, b) => b.entryDate.localeCompare(a.entryDate) || b.createdAt.localeCompare(a.createdAt))
      .map((entry) => ({
        ...entry,
        symbols: parseJsonList(entry.symbolsJson),
        tags: parseJsonList(entry.tagsJson),
        linkedTrades: (tradeIdsByJournal.get(entry.id) ?? [])
          .map((tradeId) => tradeById.get(tradeId))
          .filter((trade): trade is Trade => Boolean(trade))
          .sort((a, b) => a.tradeDate.localeCompare(b.tradeDate) || a.createdAt.localeCompare(b.createdAt))
          .map((trade) => ({
            id: trade.id,
            tradeDate: trade.tradeDate,
            symbol: getTradeDisplaySymbol(trade),
            side: trade.side,
            quantity: trade.quantity,
            priceCents: trade.priceCents,
            strategy: trade.strategy,
            setup: trade.setup
          }))
      })),
    totals: {
      cashCents,
      positionValueCents,
      equityCents,
      costBasisCents,
      realizedPnlCents,
      unrealizedPnlCents,
      totalPnlCents: realizedPnlCents + unrealizedPnlCents,
      exposurePct: equityCents ? positionValueCents / equityCents : 0,
      winRate: realizedEvents.length ? wins.length / realizedEvents.length : 0,
      profitFactor: grossLossCents ? grossWinCents / grossLossCents : wins.length ? null : 0,
      avgWinCents,
      avgLossCents,
      largestLossCents,
      tradeCount: input.trades.length,
      openPositionCount: positions.length
    }
  };
}
