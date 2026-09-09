import { describe, expect, it } from "vitest";

import { EMPTY_DRAFT, draftHasInput, draftToRequest, type Draft } from "@/hooks/useAnalysis";

function draft(overrides: Partial<Draft> = {}): Draft {
  return { ...EMPTY_DRAFT, ...overrides };
}

describe("draftToRequest", () => {
  it("sends only the fields that were filled in", () => {
    const request = draftToRequest(draft({ purchase_price: "150000", arv: "250000" }));
    expect(request.purchase_price).toBe("150000");
    expect(request.arv).toBe("250000");
    // An untouched rehab must be absent, not "0" — the engine has to be able
    // to tell "no estimate" from "costs nothing".
    expect(request).not.toHaveProperty("rehab");
    expect(request).not.toHaveProperty("monthly_rent");
  });

  it("strips currency formatting the user may paste", () => {
    expect(draftToRequest(draft({ purchase_price: "$150,000" })).purchase_price).toBe(
      "150000"
    );
  });

  it("omits an unparseable value rather than sending junk", () => {
    expect(draftToRequest(draft({ arv: "about $250k" }))).not.toHaveProperty("arv");
  });

  it("omits assumptions entirely when nothing was overridden", () => {
    // Sending an empty object would still be an override payload; omitting it
    // lets the engine's provisional defaults apply.
    expect(draftToRequest(draft({ purchase_price: "1" }))).not.toHaveProperty(
      "assumptions"
    );
  });

  it("sends assumptions that were overridden", () => {
    const request = draftToRequest(
      draft({
        purchase_price: "150000",
        assumptions: { flip: { rehab_contingency: "0.25" } },
      })
    );
    expect(request.assumptions).toEqual({ flip: { rehab_contingency: "0.25" } });
  });

  it("omits evidence and risk flags when empty", () => {
    const request = draftToRequest(draft({ purchase_price: "1" }));
    expect(request).not.toHaveProperty("evidence");
    expect(request).not.toHaveProperty("risk_flags");
  });

  it("sends declared risk flags", () => {
    const request = draftToRequest(
      draft({ purchase_price: "1", risk_flags: ["structural_concern"] })
    );
    expect(request.risk_flags).toEqual(["structural_concern"]);
  });

  it("defaults to not requesting AI narration", () => {
    // The numbers are the product. An AI call costs time and money, so it is
    // opt-in.
    expect(draftToRequest(draft({ purchase_price: "1" })).include_ai).toBe(false);
    expect(draftToRequest(draft({ purchase_price: "1" }), true).include_ai).toBe(true);
  });

  it("sends a genuine zero", () => {
    // A turnkey property really can have zero rehab, and that is different
    // from not having estimated it.
    expect(draftToRequest(draft({ rehab: "0" })).rehab).toBe("0");
  });
});

describe("draftHasInput", () => {
  it("is false for an empty draft", () => {
    expect(draftHasInput(EMPTY_DRAFT)).toBe(false);
  });

  it("is false when only evidence has been set", () => {
    expect(draftHasInput(draft({ evidence: { comp_count: 3 } }))).toBe(false);
  });

  it("is true once any money field is filled", () => {
    expect(draftHasInput(draft({ monthly_rent: "1800" }))).toBe(true);
  });

  it("is true for a zero, which is a real input", () => {
    expect(draftHasInput(draft({ rehab: "0" }))).toBe(true);
  });
});
