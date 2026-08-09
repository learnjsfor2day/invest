import { NextResponse } from "next/server";
import { z } from "zod";
import { centsFromDecimal } from "@/domain/money";
import { splitList } from "@/domain/tags";
import { addTrade } from "@/server/repository";

export const runtime = "nodejs";

const schema = z.object({
  tradeDate: z.string().trim().min(8),
  symbol: z.string().trim().min(1),
  instrument: z.string().trim().min(1).default("stock"),
  underlyingSymbol: z.string().trim().optional(),
  optionType: z.enum(["CALL", "PUT"]).optional(),
  expirationDate: z.string().trim().optional(),
  strike: z.union([z.string(), z.number()]).optional(),
  contractMultiplier: z.union([z.string(), z.number()]).optional(),
  side: z.enum(["BUY", "SELL"]),
  quantity: z.union([z.string(), z.number()]),
  price: z.union([z.string(), z.number()]),
  fees: z.union([z.string(), z.number()]).optional(),
  strategy: z.string().trim().optional(),
  setup: z.string().trim().optional(),
  notes: z.string().trim().optional(),
  tags: z.string().trim().optional()
});

export async function POST(request: Request) {
  const body = schema.parse(await request.json());
  const quantity = Number(body.quantity);
  if (!Number.isFinite(quantity) || quantity <= 0) {
    return NextResponse.json({ error: "quantity must be positive" }, { status: 400 });
  }
  const isOption = body.instrument === "option";
  if (isOption && (!body.optionType || !body.expirationDate || body.strike === undefined || body.strike === "")) {
    return NextResponse.json({ error: "option type, expiration, and strike are required" }, { status: 400 });
  }

  const contractMultiplier = Number(body.contractMultiplier || (isOption ? 100 : 1));
  if (!Number.isFinite(contractMultiplier) || contractMultiplier <= 0) {
    return NextResponse.json({ error: "contract multiplier must be positive" }, { status: 400 });
  }

  await addTrade({
    tradeDate: body.tradeDate,
    symbol: body.symbol.toUpperCase(),
    instrument: body.instrument,
    underlyingSymbol: isOption ? (body.underlyingSymbol || body.symbol).toUpperCase() : null,
    optionType: isOption ? body.optionType ?? null : null,
    expirationDate: isOption ? body.expirationDate ?? null : null,
    strikeCents: isOption ? centsFromDecimal(body.strike ?? 0) : null,
    contractMultiplier,
    side: body.side,
    quantity,
    priceCents: centsFromDecimal(body.price),
    feesCents: centsFromDecimal(body.fees ?? 0),
    strategy: body.strategy || null,
    setup: body.setup || null,
    notes: body.notes || null,
    tagsJson: JSON.stringify(splitList(body.tags))
  });

  return NextResponse.json({ ok: true });
}
