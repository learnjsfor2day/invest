import { NextResponse } from "next/server";
import { deleteJournalEntry } from "@/server/repository";

export const runtime = "nodejs";

export async function DELETE(_request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  await deleteJournalEntry(id);
  return NextResponse.json({ ok: true });
}
