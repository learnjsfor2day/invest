import { NextResponse } from "next/server";
import { deleteCashFlow } from "@/server/repository";

export const runtime = "nodejs";

export async function DELETE(_request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  await deleteCashFlow(id);
  return NextResponse.json({ ok: true });
}
