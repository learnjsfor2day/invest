import { NextResponse } from "next/server";
import { z } from "zod";
import { centsFromDecimal } from "@/domain/money";
import { updateDefaultAccount } from "@/server/repository";

export const runtime = "nodejs";

const schema = z.object({
  name: z.string().trim().min(1),
  currency: z.string().trim().min(3).max(3),
  initialCash: z.union([z.string(), z.number()])
});

export async function PATCH(request: Request) {
  const body = schema.parse(await request.json());
  await updateDefaultAccount({
    name: body.name,
    currency: body.currency.toUpperCase(),
    initialCashCents: centsFromDecimal(body.initialCash)
  });
  return NextResponse.json({ ok: true });
}
