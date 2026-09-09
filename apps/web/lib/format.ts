/**
 * Formatting for values that arrive from the API as decimal strings.
 *
 * The one rule that matters here: `null` and `undefined` render as "—", never
 * as "$0" or "0%". The backend is careful to distinguish "unknown" from
 * "zero", and throwing that distinction away at the last moment would undo it.
 */

export const EMPTY = "—";

/** Parse an API decimal string. Returns null for anything unparseable. */
export function parseDecimal(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function formatMoney(
  value: string | number | null | undefined,
  options: { decimals?: number; signed?: boolean } = {}
): string {
  const parsed = parseDecimal(value);
  if (parsed === null) return EMPTY;
  const { decimals = 0, signed = false } = options;
  const formatted = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(Math.abs(parsed));
  if (parsed < 0) return `-${formatted}`;
  return signed && parsed > 0 ? `+${formatted}` : formatted;
}

/** Compact money for tiles: $1.2M, $345K. */
export function formatMoneyCompact(value: string | number | null | undefined): string {
  const parsed = parseDecimal(value);
  if (parsed === null) return EMPTY;
  const abs = Math.abs(parsed);
  const sign = parsed < 0 ? "-" : "";
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(1)}M`;
  if (abs >= 10_000) return `${sign}$${Math.round(abs / 1_000)}K`;
  return formatMoney(parsed);
}

/** A ratio expressed as a fraction ("0.2229") rendered as a percentage. */
export function formatPercent(
  value: string | number | null | undefined,
  decimals = 1
): string {
  const parsed = parseDecimal(value);
  if (parsed === null) return EMPTY;
  return `${(parsed * 100).toFixed(decimals)}%`;
}

/** A plain ratio such as DSCR, shown to two places. */
export function formatRatio(
  value: string | number | null | undefined,
  decimals = 2
): string {
  const parsed = parseDecimal(value);
  if (parsed === null) return EMPTY;
  return parsed.toFixed(decimals);
}

export function formatNumber(value: string | number | null | undefined): string {
  const parsed = parseDecimal(value);
  if (parsed === null) return EMPTY;
  return new Intl.NumberFormat("en-US").format(parsed);
}

export function formatMonths(value: number | null | undefined): string {
  if (value === null || value === undefined) return EMPTY;
  if (value === 1) return "1 month";
  if (value % 12 === 0 && value >= 12) {
    const years = value / 12;
    return years === 1 ? "1 year" : `${years} years`;
  }
  return `${value} months`;
}

export function formatScore(value: string | number | null | undefined): string {
  const parsed = parseDecimal(value);
  if (parsed === null) return EMPTY;
  return Math.round(parsed).toString();
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return EMPTY;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return EMPTY;
  return date.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return EMPTY;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return EMPTY;
  return date.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/** Turn a snake_case key into a readable label. */
export function humanise(value: string): string {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase())
    .replace(/\bArv\b/g, "ARV")
    .replace(/\bRoi\b/g, "ROI")
    .replace(/\bDscr\b/g, "DSCR")
    .replace(/\bHoa\b/g, "HOA")
    .replace(/\bLtv\b/g, "LTV")
    .replace(/\bCapex\b/g, "CapEx")
    .replace(/\bBrrrr\b/g, "BRRRR")
    .replace(/\bFsbo\b/g, "FSBO")
    .replace(/\bDom\b/g, "DOM");
}

/** Format a criterion's value according to its declared unit. */
export function formatByUnit(
  value: string | null | undefined,
  unit: "currency" | "percent" | "ratio" | "months"
): string {
  switch (unit) {
    case "percent":
      return formatPercent(value);
    case "ratio":
      return formatRatio(value);
    case "months":
      return formatMonths(parseDecimal(value));
    default:
      return formatMoney(value);
  }
}
