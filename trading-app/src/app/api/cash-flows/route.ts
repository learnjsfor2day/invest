import { NextResponse } from "next/server";
import { z } from "zod";
import { centsFromDecimal } from "@/domain/money";
import { addCashFlow } from "@/server/repository";

export const runtime = "nodejs";

const schema = z.object({
  flowDate: z.string().trim().min(8),
  type: z.enum(["DEPOSIT", "WITHDRAWAL", "DIVIDEND", "INTEREST", "FEE", "TAX", "ADJUSTMENT"]),
  amount: z.union([z.string(), z.number()]),
  symbol: z.string().trim().optional(),
  notes: z.string().trim().optional()
});

export async function POST(request: Request) {
  const body = schema.parse(await request.json());
  await addCashFlow({
    flowDate: body.flowDate,
    type: body.type,
    amountCents: Math.abs(centsFromDecimal(body.amount)),
    symbol: body.symbol ? body.symbol.toUpperCase() : null,
    notes: body.notes || null
  });
  return NextResponse.json({ ok: true });
}
