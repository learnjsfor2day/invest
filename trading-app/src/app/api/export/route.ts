import { NextResponse } from "next/server";
import { getSnapshot } from "@/server/repository";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const snapshot = await getSnapshot();
  const payload = {
    exportedAt: new Date().toISOString(),
    version: 1,
    snapshot
  };

  return new NextResponse(JSON.stringify(payload, null, 2), {
    headers: {
      "content-type": "application/json; charset=utf-8",
      "content-disposition": `attachment; filename="trading-export-${new Date()
        .toISOString()
        .slice(0, 10)}.json"`
    }
  });
}
