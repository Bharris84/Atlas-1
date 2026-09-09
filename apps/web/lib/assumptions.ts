/**
 * The editable assumption surface.
 *
 * Atlas's position is that every number driving a result must be visible and
 * changeable. This module declares that surface as data, so the UI renders it
 * from one list rather than from hand-written forms that drift out of sync
 * with the engine.
 *
 * Paths are dotted routes into the assumptions object the API accepts. Only
 * fields the user has actually touched are sent, so anything untouched keeps
 * the engine's provisional default rather than being frozen into the request.
 */

export type FieldKind = "money" | "percent" | "months" | "years" | "ratio";

export interface AssumptionField {
  path: string;
  label: string;
  kind: FieldKind;
  help?: string;
}

export interface AssumptionGroup {
  key: string;
  title: string;
  description: string;
  fields: AssumptionField[];
}

export const ASSUMPTION_GROUPS: AssumptionGroup[] = [
  {
    key: "transaction",
    title: "Transaction costs",
    description: "What it costs to get in and out of the property.",
    fields: [
      {
        path: "transaction.purchase_closing_percent",
        label: "Purchase closing",
        kind: "percent",
        help: "Title, escrow and recording, as a share of the purchase price.",
      },
      {
        path: "transaction.sale_commission_percent",
        label: "Sale commission",
        kind: "percent",
      },
      {
        path: "transaction.sale_closing_percent",
        label: "Sale closing",
        kind: "percent",
        help: "Seller-paid title, transfer tax and concessions.",
      },
      {
        path: "transaction.miscellaneous_costs",
        label: "Miscellaneous",
        kind: "money",
      },
    ],
  },
  {
    key: "holding",
    title: "Holding costs",
    description: "Carrying costs while the property is owned but not earning.",
    fields: [
      { path: "holding.annual_taxes", label: "Annual taxes", kind: "money" },
      { path: "holding.annual_insurance", label: "Annual insurance", kind: "money" },
      { path: "holding.monthly_utilities", label: "Monthly utilities", kind: "money" },
      { path: "holding.monthly_hoa", label: "Monthly HOA", kind: "money" },
    ],
  },
  {
    key: "flip",
    title: "Fix & flip",
    description: "Rehab, hold period, financing and the buy-box thresholds.",
    fields: [
      {
        path: "flip.rehab_contingency",
        label: "Rehab contingency",
        kind: "percent",
        help: "Added to the rehab budget. Overruns are the most common way a flip misses.",
      },
      { path: "flip.holding_months", label: "Holding period", kind: "months" },
      { path: "flip.minimum_net_profit", label: "Minimum profit", kind: "money" },
      { path: "flip.minimum_roi", label: "Minimum ROI", kind: "percent" },
      {
        path: "flip.financing.loan_to_purchase",
        label: "Loan to purchase",
        kind: "percent",
      },
      { path: "flip.financing.loan_to_rehab", label: "Loan to rehab", kind: "percent" },
      {
        path: "flip.financing.annual_interest_rate",
        label: "Interest rate",
        kind: "percent",
      },
      { path: "flip.financing.points", label: "Points", kind: "percent" },
      { path: "flip.financing.lender_fees_flat", label: "Lender fees", kind: "money" },
    ],
  },
  {
    key: "rental",
    title: "Rental operating expenses",
    description:
      "Management is charged on collected rent; maintenance and CapEx on gross rent, because a vacant unit still ages.",
    fields: [
      { path: "rental.vacancy_percent", label: "Vacancy", kind: "percent" },
      { path: "rental.management_percent", label: "Management", kind: "percent" },
      { path: "rental.maintenance_percent", label: "Maintenance", kind: "percent" },
      { path: "rental.capex_percent", label: "CapEx", kind: "percent" },
      { path: "rental.annual_taxes", label: "Annual taxes", kind: "money" },
      { path: "rental.annual_insurance", label: "Annual insurance", kind: "money" },
      { path: "rental.monthly_hoa", label: "Monthly HOA", kind: "money" },
      {
        path: "rental.minimum_monthly_cash_flow",
        label: "Minimum cash flow",
        kind: "money",
      },
      {
        path: "rental.minimum_cash_on_cash",
        label: "Minimum cash-on-cash",
        kind: "percent",
      },
      { path: "rental.target_dscr", label: "Target DSCR", kind: "ratio" },
      {
        path: "rental.financing.loan_to_purchase",
        label: "Loan to purchase",
        kind: "percent",
      },
      {
        path: "rental.financing.annual_interest_rate",
        label: "Interest rate",
        kind: "percent",
      },
      {
        path: "rental.financing.amortization_years",
        label: "Amortisation",
        kind: "years",
      },
    ],
  },
  {
    key: "wholesale",
    title: "Wholesale",
    description:
      "Priced from the end buyer's deal, not a 70% rule. These are the buyer's requirements plus our fee.",
    fields: [
      {
        path: "wholesale.target_assignment_fee",
        label: "Assignment fee target",
        kind: "money",
      },
      {
        path: "wholesale.buyer_profit_percent_of_arv",
        label: "Buyer profit target",
        kind: "percent",
        help: "What the end buyer needs to earn, as a share of ARV.",
      },
      {
        path: "wholesale.buyer_profit_floor",
        label: "Buyer profit floor",
        kind: "money",
        help: "On a cheap house, a percentage of ARV is less than any investor will work for.",
      },
      {
        path: "wholesale.risk_buffer_percent_of_arv",
        label: "Risk buffer",
        kind: "percent",
        help: "Held back because the buyer's own inspection will find things ours did not.",
      },
      {
        path: "wholesale.buyer_holding_months",
        label: "Buyer holding period",
        kind: "months",
      },
    ],
  },
  {
    key: "brrrr",
    title: "BRRRR",
    description: "Refinance terms and how much capital may stay trapped.",
    fields: [
      { path: "brrrr.refinance_ltv", label: "Refinance LTV", kind: "percent" },
      {
        path: "brrrr.max_cash_left_in_deal",
        label: "Max cash left in deal",
        kind: "money",
        help: "The number that decides whether BRRRR is the right strategy.",
      },
      {
        path: "brrrr.minimum_equity_percent",
        label: "Minimum equity",
        kind: "percent",
      },
      { path: "brrrr.seasoning_months", label: "Seasoning period", kind: "months" },
      { path: "brrrr.refinance_rate", label: "Refinance rate", kind: "percent" },
      {
        path: "brrrr.refinance_closing_percent",
        label: "Refinance closing",
        kind: "percent",
      },
    ],
  },
  {
    key: "seller_finance",
    title: "Seller financing",
    description: "Terms offered by the seller, and when the balloon comes due.",
    fields: [
      {
        path: "seller_finance.down_payment_percent",
        label: "Down payment",
        kind: "percent",
      },
      {
        path: "seller_finance.annual_interest_rate",
        label: "Interest rate",
        kind: "percent",
      },
      {
        path: "seller_finance.amortization_years",
        label: "Amortisation",
        kind: "years",
      },
      { path: "seller_finance.balloon_years", label: "Balloon", kind: "years" },
      {
        path: "seller_finance.closing_costs_percent",
        label: "Closing costs",
        kind: "percent",
      },
    ],
  },
];

export const ALL_ASSUMPTION_FIELDS: AssumptionField[] = ASSUMPTION_GROUPS.flatMap(
  (group) => group.fields
);

export function findField(path: string): AssumptionField | undefined {
  return ALL_ASSUMPTION_FIELDS.find((field) => field.path === path);
}

/** Read a dotted path out of a nested object. */
export function getPath(source: Record<string, any> | null | undefined, path: string): any {
  if (!source) return undefined;
  return path.split(".").reduce<any>((node, key) => {
    if (node === null || node === undefined || typeof node !== "object") return undefined;
    return node[key];
  }, source);
}

/** Immutably set a dotted path, creating intermediate objects as needed. */
export function setPath(
  source: Record<string, any>,
  path: string,
  value: unknown
): Record<string, any> {
  const [head, ...rest] = path.split(".");
  const next = { ...source };
  if (rest.length === 0) {
    next[head] = value;
    return next;
  }
  const child =
    typeof next[head] === "object" && next[head] !== null ? next[head] : {};
  next[head] = setPath(child, rest.join("."), value);
  return next;
}

/** Immutably remove a dotted path, pruning objects left empty. */
export function deletePath(
  source: Record<string, any>,
  path: string
): Record<string, any> {
  const [head, ...rest] = path.split(".");
  if (!(head in source)) return source;
  const next = { ...source };
  if (rest.length === 0) {
    delete next[head];
    return next;
  }
  if (typeof next[head] !== "object" || next[head] === null) return next;
  const child = deletePath(next[head], rest.join("."));
  if (Object.keys(child).length === 0) {
    delete next[head];
  } else {
    next[head] = child;
  }
  return next;
}

/**
 * Convert a form field's display value to the string the API expects.
 * Percent fields are entered as "8" and sent as "0.08".
 */
export function toApiValue(raw: string, kind: FieldKind): string | null {
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  const numeric = Number(trimmed.replace(/[$,%\s,]/g, ""));
  if (!Number.isFinite(numeric)) return null;
  if (kind === "percent") return String(numeric / 100);
  return String(numeric);
}

/** Convert an API value back to what the user should see in the field. */
export function toDisplayValue(
  value: string | number | null | undefined,
  kind: FieldKind
): string {
  if (value === null || value === undefined || value === "") return "";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return String(value);
  if (kind === "percent") {
    // 0.0825 -> "8.25", without trailing float noise.
    return String(Number((numeric * 100).toFixed(4)));
  }
  return String(Number(numeric.toFixed(4)));
}

export function unitSuffix(kind: FieldKind): string {
  switch (kind) {
    case "percent":
      return "%";
    case "months":
      return "mo";
    case "years":
      return "yr";
    default:
      return "";
  }
}
