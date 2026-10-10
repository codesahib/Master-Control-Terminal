import type { TransactionType } from "../types";

const formatters = new Map<string, Intl.NumberFormat>();

function numberFormat(key: string, options: Intl.NumberFormatOptions) {
  let formatter = formatters.get(key);
  if (!formatter) {
    formatter = new Intl.NumberFormat("en-CA", options);
    formatters.set(key, formatter);
  }
  return formatter;
}

function isNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

export function money(value: number | null | undefined, currency = "CAD", digits = 2) {
  if (!isNumber(value)) return "–";
  return numberFormat(`m:${currency}:${digits}`, {
    style: "currency",
    currency,
    currencyDisplay: "narrowSymbol",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value).replace(/^\$/, currency === "USD" ? "US$" : "$").replace(/^-\$/, currency === "USD" ? "−US$" : "−$");
}

export function signedMoney(value: number | null | undefined, currency = "CAD") {
  if (!isNumber(value)) return "–";
  const text = money(Math.abs(value), currency);
  return value < 0 ? `−${text}` : `+${text}`;
}

export function compactMoney(value: number | null | undefined, currency = "CAD") {
  if (!isNumber(value)) return "–";
  return numberFormat(`c:${currency}`, { style: "currency", currency, currencyDisplay: "narrowSymbol", notation: "compact", maximumFractionDigits: 1 }).format(value);
}

export function pct(value: number | null | undefined, signed = true) {
  if (!isNumber(value)) return "–";
  const text = `${Math.abs(value).toFixed(2)}%`;
  if (!signed) return text;
  return value < 0 ? `−${text}` : `+${text}`;
}

export function quantity(value: number | null | undefined) {
  if (!isNumber(value)) return "–";
  return numberFormat("q", { maximumFractionDigits: 6 }).format(value);
}

export function shortDate(value: string | null | undefined) {
  if (!value) return "–";
  const date = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("en-CA", { month: "short", day: "numeric", year: "numeric" });
}

export function timeAgo(value: string | null | undefined) {
  if (!value) return "never";
  const raw = /[zZ]|[+-]\d\d:?\d\d$/.test(value) ? value : `${value}Z`;
  const minutes = Math.round((Date.now() - new Date(raw).getTime()) / 60000);
  if (!Number.isFinite(minutes)) return "unknown";
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  if (minutes < 60 * 48) return `${Math.round(minutes / 60)}h ago`;
  return `${Math.round(minutes / 1440)}d ago`;
}

export const TYPE_LABELS: Record<TransactionType, string> = {
  contribution: "Contribution",
  investment_buy: "Buy",
  investment_sell: "Sell",
  transfer: "Transfer",
  dividend_interest: "Dividend / interest",
  dividend_reinvestment: "Reinvest",
  quantity_adjustment: "Adjust units",
  currency_exchange: "Exchange",
  withdrawal: "Withdrawal",
};

export const STATUS_LABELS: Record<string, { label: string; tone: string }> = {
  ok: { label: "Live", tone: "pos" },
  stale: { label: "Stale", tone: "warn" },
  missing: { label: "No price", tone: "neg" },
  missing_quantity: { label: "Needs value", tone: "warn" },
  currency_mismatch: { label: "Currency mismatch", tone: "neg" },
  cash: { label: "Cash", tone: "n" },
  mixed: { label: "Mixed", tone: "info" },
};

export function errorMessage(error: any, fallback = "Something went wrong. Try again.") {
  const detail = error?.response?.data?.detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => (item?.loc ? `${item.loc.filter((part: unknown) => part !== "body").join(".")}: ${item.msg}` : item?.msg || String(item))).join("; ");
  }
  if (typeof detail === "string" && detail) return detail;
  if (error?.response?.status === 404) return "Not found.";
  if (error?.message === "Network Error") return "Cannot reach the API. Is it running?";
  return fallback;
}
