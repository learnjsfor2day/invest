export function splitList(input?: string | null): string[] {
  if (!input) return [];
  return input
    .split(/[,，\s]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function parseJsonList(input: string | null): string[] {
  if (!input) return [];
  try {
    const value = JSON.parse(input);
    return Array.isArray(value) ? value.filter((item) => typeof item === "string") : [];
  } catch {
    return [];
  }
}
