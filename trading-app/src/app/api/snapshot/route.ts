import { NextResponse } from "next/server";
import { getSnapshot } from "@/server/repository";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const snapshot = await getSnapshot();
  return NextResponse.json(snapshot);
}
