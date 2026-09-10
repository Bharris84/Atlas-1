import { describe, expect, it } from "vitest";

import {
  ALL_ASSUMPTION_FIELDS,
  ASSUMPTIONS_SCHEMA_VERSION,
  ASSUMPTION_GROUPS,
  deletePath,
  describeAssumptionPath,
  getPath,
  setPath,
  toApiValue,
  toDisplayValue,
} from "@/lib/assumptions";

describe("path helpers", () => {
  it("reads a nested value", () => {
    expect(getPath({ flip: { rehab_contingency: "0.15" } }, "flip.rehab_contingency")).toBe(
      "0.15"
    );
  });

  it("returns undefined for a missing path rather than throwing", () => {
    expect(getPath({}, "flip.financing.points")).toBeUndefined();
    expect(getPath(null, "flip.points")).toBeUndefined();
  });

  it("creates intermediate objects when setting", () => {
    expect(setPath({}, "flip.financing.points", "0.03")).toEqual({
      flip: { financing: { points: "0.03" } },
    });
  });

  it("does not mutate the original", () => {
    const original = { flip: { holding_months: "6" } };
    setPath(original, "flip.holding_months", "9");
    expect(original.flip.holding_months).toBe("6");
  });

  it("preserves sibling values", () => {
    const result = setPath(
      { flip: { holding_months: "6", minimum_roi: "0.2" } },
      "flip.holding_months",
      "9"
    );
    expect(result.flip).toEqual({ holding_months: "9", minimum_roi: "0.2" });
  });

  it("prunes objects left empty by a delete", () => {
    // An empty `{flip: {}}` would be sent as an override of nothing, so it is
    // removed entirely and the engine default applies.
    expect(deletePath({ flip: { points: "0.03" } }, "flip.points")).toEqual({});
  });

  it("keeps siblings when deleting", () => {
    expect(
      deletePath({ flip: { points: "0.03", holding_months: "6" } }, "flip.points")
    ).toEqual({ flip: { holding_months: "6" } });
  });

  it("deleting an absent path is a no-op", () => {
    const source = { flip: { points: "0.03" } };
    expect(deletePath(source, "rental.vacancy_percent")).toEqual(source);
  });
});

describe("percent conversion", () => {
  it("sends a percentage as a fraction", () => {
    // The user types 8; the engine expects 0.08.
    expect(toApiValue("8", "percent")).toBe("0.08");
  });

  it("shows a fraction as a percentage", () => {
    expect(toDisplayValue("0.0825", "percent")).toBe("8.25");
  });

  it("round-trips without drift", () => {
    expect(toDisplayValue(toApiValue("15", "percent"), "percent")).toBe("15");
  });

  it("leaves money untouched", () => {
    expect(toApiValue("30000", "money")).toBe("30000");
    expect(toDisplayValue("30000", "money")).toBe("30000");
  });

  it("strips formatting a user might paste", () => {
    expect(toApiValue("$30,000", "money")).toBe("30000");
    expect(toApiValue("8%", "percent")).toBe("0.08");
  });

  it("treats an empty field as cleared, not as zero", () => {
    // Clearing a field must restore the engine default, so it returns null
    // rather than "0" — which would be a real override meaning "zero".
    expect(toApiValue("", "money")).toBeNull();
    expect(toApiValue("   ", "percent")).toBeNull();
  });

  it("rejects unparseable input", () => {
    expect(toApiValue("abc", "money")).toBeNull();
  });

  it("renders an absent value as an empty field", () => {
    expect(toDisplayValue(null, "money")).toBe("");
    expect(toDisplayValue(undefined, "percent")).toBe("");
  });
});

describe("the assumption surface", () => {
  it("exposes every strategy's assumptions", () => {
    const keys = ASSUMPTION_GROUPS.map((group) => group.key);
    expect(keys).toEqual(
      expect.arrayContaining([
        "transaction",
        "holding",
        "flip",
        "rental",
        "wholesale",
        "brrrr",
        "seller_finance",
      ])
    );
  });

  it("covers the assumptions the product requires to be editable", () => {
    const paths = ALL_ASSUMPTION_FIELDS.map((field) => field.path);
    for (const required of [
      "flip.rehab_contingency",
      "flip.holding_months",
      "transaction.purchase_closing_percent",
      "transaction.sale_commission_percent",
      "rental.vacancy_percent",
      "rental.management_percent",
      "rental.maintenance_percent",
      "rental.capex_percent",
      "wholesale.target_assignment_fee",
      "wholesale.buyer_profit_percent_of_arv",
      "brrrr.refinance_ltv",
      "brrrr.max_cash_left_in_deal",
      "seller_finance.down_payment_percent",
    ]) {
      expect(paths).toContain(required);
    }
  });

  it("has no duplicate paths", () => {
    const paths = ALL_ASSUMPTION_FIELDS.map((field) => field.path);
    expect(new Set(paths).size).toBe(paths.length);
  });

  it("labels every field", () => {
    for (const field of ALL_ASSUMPTION_FIELDS) {
      expect(field.label.length).toBeGreaterThan(0);
    }
  });
});

describe("tri-state operating expenses", () => {
  const EXPENSES = [
    "holding.annual_taxes",
    "holding.annual_insurance",
    "holding.monthly_hoa",
    "holding.monthly_utilities",
    "rental.annual_taxes",
    "rental.annual_insurance",
    "rental.monthly_hoa",
  ];

  it("marks every property-specific expense as unknownable", () => {
    for (const path of EXPENSES) {
      const field = ALL_ASSUMPTION_FIELDS.find((f) => f.path === path);
      expect(field, path).toBeDefined();
      expect(field?.unknownable, path).toBe(true);
    }
  });

  it("marks nothing else as unknownable", () => {
    // Everything else genuinely has a defensible default. Tagging a field
    // "not known" when Atlas has in fact chosen a number would be the same
    // false claim in the opposite direction.
    const tagged = ALL_ASSUMPTION_FIELDS.filter((f) => f.unknownable).map((f) => f.path);
    expect(tagged.sort()).toEqual([...EXPENSES].sort());
  });

  it("sends an explicit zero rather than dropping it", () => {
    // The whole point of the tri-state: "0" must survive as a value, while a
    // blank field clears the override and returns to unknown.
    expect(toApiValue("0", "money")).toBe("0");
    expect(toApiValue("", "money")).toBeNull();
    expect(toApiValue("   ", "money")).toBeNull();
  });

  it("renders an unknown value as blank, not as zero", () => {
    expect(toDisplayValue(null, "money")).toBe("");
    expect(toDisplayValue(undefined, "money")).toBe("");
    expect(toDisplayValue("0", "money")).toBe("0");
  });
});

describe("describeAssumptionPath", () => {
  it("names an expense with the section it belongs to", () => {
    // holding.annual_taxes and rental.annual_taxes are separately editable and
    // can legitimately differ, so "Annual taxes" alone would be ambiguous.
    expect(describeAssumptionPath("holding.annual_taxes")).toBe(
      "Annual taxes — holding costs"
    );
    expect(describeAssumptionPath("rental.annual_taxes")).toBe(
      "Annual taxes — rental operating expenses"
    );
  });

  it("returns null for a plain input so the caller can fall back", () => {
    expect(describeAssumptionPath("purchase_price")).toBeNull();
    expect(describeAssumptionPath("arv")).toBeNull();
  });
});

describe("schema version", () => {
  it("is a positive integer the API can compare against", () => {
    expect(Number.isInteger(ASSUMPTIONS_SCHEMA_VERSION)).toBe(true);
    expect(ASSUMPTIONS_SCHEMA_VERSION).toBeGreaterThan(0);
  });
});
