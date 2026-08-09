export function centsFromDecimal(value: string | number): number {
  const raw = typeof value === "number" ? value.toString() : value.trim();
  if (!raw) return 0;
  const normalized = raw.replace(/,/g, "");
  const sign = normalized.startsWith("-") ? -1 : 1;
  const body = normalized.replace(/^[+-]/, "");
  const [whole = "0", fraction = ""] = body.split(".");
  const cents = `${fraction}00`.slice(0, 2);
  return sign * (Number.parseInt(whole || "0", 10) * 100 + Number.parseInt(cents || "0", 10));
}

export function formatMoney(cents: number, currency = "USD") {
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency,
    maximumFractionDigits: 2
  }).format(cents / 100);
}

export function formatNumber(value: number, digits = 2) {
  return new Intl.NumberFormat("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits
  }).format(value);
}

export function formatPercent(value: number) {
  if (!Number.isFinite(value)) return "0.0%";
  return new Intl.NumberFormat("zh-CN", {
    style: "percent",
    minimumFractionDigits: 1,
    maximumFractionDigits: 1
  }).format(value);
}
