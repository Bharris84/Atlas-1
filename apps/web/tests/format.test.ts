import { describe, expect, it } from "vitest";

import {
  EMPTY,
  formatByUnit,
  formatMoney,
  formatMoneyCompact,
  formatMonths,
  formatNumber,
  formatPercent,
  formatRatio,
  formatScore,
  humanise,
  parseDecimal,
} from "@/lib/format";

/**
 * The rule these tests exist to protect: the backend distinguishes "unknown"
 * from "zero", and the UI must not undo that at the last moment.
 */
describe("unknown is never rendered as zero", () => {
  it.each([null, undefined, ""])("money renders %s as an em dash", (value) => {
    expect(formatMoney(value as never)).toBe(EMPTY);
  });

  it.each([null, undefined])("percent renders %s as an em dash", (value) => {
    expect(formatPercent(value as never)).toBe(EMPTY);
  });

  it("a null DSCR renders as an em dash, not 0.00", () => {
    // A property with no debt has no coverage ratio. "0.00" would read as
    // "cannot cover its debt", which is the opposite of the truth.
    expect(formatRatio(null)).toBe(EMPTY);
  });

  it("an actual zero still renders as zero", () => {
    expect(formatMoney("0")).toBe("$0");
    expect(formatPercent("0")).toBe("0.0%");
    expect(formatRatio("0")).toBe("0.00");
  });
});

describe("formatMoney", () => {
  it("formats whole dollars by default", () => {
    expect(formatMoney("150000.00")).toBe("$150,000");
  });

  it("keeps the sign on a loss", () => {
    expect(formatMoney("-12500")).toBe("-$12,500");
  });

  it("can show cents", () => {
    expect(formatMoney("1234.56", { decimals: 2 })).toBe("$1,234.56");
  });

  it("marks a gain when asked", () => {
    expect(formatMoney("5000", { signed: true })).toBe("+$5,000");
  });

  it("does not lose precision on a large decimal string", () => {
    expect(formatMoney("12000000.49")).toBe("$12,000,000");
  });
});

describe("formatMoneyCompact", () => {
  it.each([
    ["2500000", "$2.5M"],
    ["345000", "$345K"],
    ["-120000", "-$120K"],
    ["950", "$950"],
  ])("formats %s as %s", (input, expected) => {
    expect(formatMoneyCompact(input)).toBe(expected);
  });
});

describe("formatPercent", () => {
  it("converts a fraction to a percentage", () => {
    expect(formatPercent("0.2229")).toBe("22.3%");
  });

  it("handles a negative return", () => {
    expect(formatPercent("-0.0838")).toBe("-8.4%");
  });
});

describe("formatMonths", () => {
  it.each([
    [1, "1 month"],
    [6, "6 months"],
    [12, "1 year"],
    [60, "5 years"],
    [null, EMPTY],
  ])("formats %s as %s", (input, expected) => {
    expect(formatMonths(input as never)).toBe(expected);
  });
});

describe("humanise", () => {
  it("expands snake_case", () => {
    expect(humanise("purchase_price")).toBe("Purchase Price");
  });

  it.each([
    ["arv", "ARV"],
    ["roi", "ROI"],
    ["dscr", "DSCR"],
    ["capex", "CapEx"],
    ["brrrr", "BRRRR"],
    ["long_DOM", "Long DOM"],
  ])("keeps %s as a domain term", (input, expected) => {
    expect(humanise(input)).toBe(expected);
  });
});

describe("formatByUnit", () => {
  it("routes each unit to the right formatter", () => {
    expect(formatByUnit("30000", "currency")).toBe("$30,000");
    expect(formatByUnit("0.2", "percent")).toBe("20.0%");
    expect(formatByUnit("1.25", "ratio")).toBe("1.25");
    expect(formatByUnit("6", "months")).toBe("6 months");
  });
});

describe("parseDecimal", () => {
  it("parses an API decimal string", () => {
    expect(parseDecimal("150000.00")).toBe(150000);
  });

  it("returns null rather than NaN for junk", () => {
    expect(parseDecimal("not a number")).toBeNull();
  });
});

describe("formatScore and formatNumber", () => {
  it("rounds a score to a whole number", () => {
    expect(formatScore("84.1581")).toBe("84");
  });

  it("groups thousands", () => {
    expect(formatNumber("1450")).toBe("1,450");
  });
});
