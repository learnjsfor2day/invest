type TradeLike = {
  symbol: string;
  instrument: string;
  quantity: number;
  priceCents: number;
  feesCents?: number | null;
  underlyingSymbol?: string | null;
  optionType?: string | null;
  expirationDate?: string | null;
  strikeCents?: number | null;
  contractMultiplier?: number | null;
};

export function isOptionTrade(trade: Pick<TradeLike, "instrument">) {
  return trade.instrument === "option";
}

export function optionStrikeLabel(strikeCents?: number | null) {
  if (strikeCents === null || strikeCents === undefined) return "";
  const value = strikeCents / 100;
  return Number.isInteger(value) ? String(value) : value.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
}

export function getTradeUnderlying(trade: Pick<TradeLike, "symbol" | "underlyingSymbol">) {
  return (trade.underlyingSymbol || trade.symbol).toUpperCase();
}

export function getContractMultiplier(trade: Pick<TradeLike, "instrument" | "contractMultiplier">) {
  const value = Number(trade.contractMultiplier);
  if (Number.isFinite(value) && value > 0) return value;
  return isOptionTrade(trade) ? 100 : 1;
}

export function getTradePositionKey(
  trade: Pick<
    TradeLike,
    "symbol" | "instrument" | "underlyingSymbol" | "optionType" | "expirationDate" | "strikeCents"
  >
) {
  if (!isOptionTrade(trade)) {
    return `${trade.instrument}:${trade.symbol.toUpperCase()}`;
  }

  const underlying = getTradeUnderlying(trade);
  const optionType = (trade.optionType || "").toUpperCase();
  const expiration = trade.expirationDate || "";
  const strike = trade.strikeCents ?? "";
  return `option:${underlying}:${expiration}:${strike}:${optionType}`;
}

export function getTradeDisplaySymbol(
  trade: Pick<
    TradeLike,
    "symbol" | "instrument" | "underlyingSymbol" | "optionType" | "expirationDate" | "strikeCents"
  >
) {
  if (!isOptionTrade(trade)) return trade.symbol.toUpperCase();

  const underlying = getTradeUnderlying(trade);
  const optionType = (trade.optionType || "").toUpperCase() === "PUT" ? "P" : "C";
  const strike = optionStrikeLabel(trade.strikeCents);
  return `${underlying} ${trade.expirationDate || "未定"} ${strike}${optionType}`;
}

export function getTradeGrossCents(
  trade: Pick<TradeLike, "instrument" | "quantity" | "priceCents" | "contractMultiplier">
) {
  return Math.round(Number(trade.quantity) * Number(trade.priceCents) * getContractMultiplier(trade));
}

export function inferTradeDirection(
  trade: Pick<TradeLike, "instrument" | "optionType">
): "LONG" | "SHORT" {
  if (isOptionTrade(trade) && (trade.optionType || "").toUpperCase() === "PUT") {
    return "SHORT";
  }
  return "LONG";
}
