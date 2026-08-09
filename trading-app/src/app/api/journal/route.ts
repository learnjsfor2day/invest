import { NextResponse } from "next/server";
import { z } from "zod";
import { centsFromDecimal } from "@/domain/money";
import { splitList } from "@/domain/tags";
import { addJournalEntry } from "@/server/repository";

export const runtime = "nodejs";

const schema = z.object({
  entryDate: z.string().trim().min(8),
  title: z.string().trim().min(1),
  mood: z.string().trim().optional(),
  strategy: z.string().trim().optional(),
  setup: z.string().trim().optional(),
  timeframe: z.string().trim().optional(),
  direction: z.string().trim().optional(),
  result: z.string().trim().optional(),
  marketRegime: z.string().trim().optional(),
  catalyst: z.string().trim().optional(),
  confidence: z.union([z.string(), z.number()]).optional(),
  plannedEntry: z.union([z.string(), z.number()]).optional(),
  plannedStop: z.union([z.string(), z.number()]).optional(),
  plannedTarget: z.union([z.string(), z.number()]).optional(),
  plannedRisk: z.union([z.string(), z.number()]).optional(),
  plannedSize: z.union([z.string(), z.number()]).optional(),
  actualEntry: z.union([z.string(), z.number()]).optional(),
  actualExit: z.union([z.string(), z.number()]).optional(),
  maxFavorable: z.union([z.string(), z.number()]).optional(),
  maxAdverse: z.union([z.string(), z.number()]).optional(),
  rMultiple: z.union([z.string(), z.number()]).optional(),
  executionScore: z.union([z.string(), z.number()]).optional(),
  disciplineScore: z.union([z.string(), z.number()]).optional(),
  followedPlan: z.string().trim().optional(),
  marketContext: z.string().trim().optional(),
  thesis: z.string().trim().optional(),
  plan: z.string().trim().optional(),
  review: z.string().trim().optional(),
  mistakes: z.string().trim().optional(),
  lessons: z.string().trim().optional(),
  symbols: z.string().trim().optional(),
  tags: z.string().trim().optional(),
  tradeIds: z.union([z.string(), z.array(z.string())]).optional()
});

function optionalCents(value: string | number | undefined) {
  if (value === undefined || value === "") return null;
  return centsFromDecimal(value);
}

function optionalNumber(value: string | number | undefined) {
  if (value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function optionalInteger(value: string | number | undefined) {
  const parsed = optionalNumber(value);
  return parsed === null ? null : Math.round(parsed);
}

function normalizeIds(value: string | string[] | undefined) {
  if (!value) return [];
  return Array.isArray(value) ? value : [value];
}

export async function POST(request: Request) {
  const body = schema.parse(await request.json());
  await addJournalEntry({
    entryDate: body.entryDate,
    title: body.title,
    mood: body.mood || null,
    strategy: body.strategy || null,
    setup: body.setup || null,
    timeframe: body.timeframe || null,
    direction: body.direction || null,
    result: body.result || null,
    marketRegime: body.marketRegime || null,
    catalyst: body.catalyst || null,
    confidence: optionalInteger(body.confidence),
    plannedEntryCents: optionalCents(body.plannedEntry),
    plannedStopCents: optionalCents(body.plannedStop),
    plannedTargetCents: optionalCents(body.plannedTarget),
    plannedRiskCents: optionalCents(body.plannedRisk),
    plannedSize: optionalNumber(body.plannedSize),
    actualEntryCents: optionalCents(body.actualEntry),
    actualExitCents: optionalCents(body.actualExit),
    maxFavorableCents: optionalCents(body.maxFavorable),
    maxAdverseCents: optionalCents(body.maxAdverse),
    rMultiple: optionalNumber(body.rMultiple),
    executionScore: optionalInteger(body.executionScore),
    disciplineScore: optionalInteger(body.disciplineScore),
    followedPlan: body.followedPlan ? body.followedPlan === "true" : null,
    marketContext: body.marketContext || null,
    thesis: body.thesis || null,
    plan: body.plan || null,
    review: body.review || null,
    mistakes: body.mistakes || null,
    lessons: body.lessons || null,
    symbolsJson: JSON.stringify(splitList(body.symbols)),
    tagsJson: JSON.stringify(splitList(body.tags)),
    linkedTradeIds: normalizeIds(body.tradeIds)
  });
  return NextResponse.json({ ok: true });
}
