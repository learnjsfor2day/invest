import { NextResponse } from "next/server";
import { z } from "zod";
import { centsFromDecimal } from "@/domain/money";
import { addPriceMark } from "@/server/repository";

export const runtime = "nodejs";

const schema = z.object({
  symbol: z.string().trim().min(1),
  markedAt: z.string().trim().min(8),
  price: z.union([z.string(), z.number()]),
  source: z.string().trim().optional()
});

export async function POST(request: Request) {
  const body = schema.parse(await request.json());
  await addPriceMark({
    symbol: body.symbol.toUpperCase(),
    markedAt: body.markedAt,
    priceCents: centsFromDecimal(body.price),
    source: body.source || "manual"
  });
  return NextResponse.json({ ok: true });
}
