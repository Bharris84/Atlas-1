import { expect, test, type Page } from "@playwright/test";

/**
 * The V0.1 definition of done, walked end to end:
 * create a property, enter the numbers, compare every strategy, get a
 * recommendation with confidence and risks, change an assumption and watch the
 * numbers move, save it, and reopen it later.
 */

const UNIQUE = Date.now();
const ADDRESS = `${UNIQUE} Magnolia Street`;

/** The strategies table. Scoped by name because the capital efficiency table
 * reuses several row labels ("Profit", "Capital deployed"). */
function strategyTable(page: Page) {
  return page.getByRole("table", { name: "Strategies compared" });
}

async function fillDealInputs(page: Page) {
  await page.getByLabel("Purchase price", { exact: true }).fill("150000");
  await page.getByLabel("After-repair value (ARV)").fill("250000");
  await page.getByLabel("Rehab", { exact: true }).fill("45000");
  await page.getByLabel("Monthly rent").fill("1800");
}

test.describe("Deal analyzer", () => {
  test("underwrites all five strategies from manually entered numbers", async ({ page }) => {
    await page.goto("/analyzer");
    await fillDealInputs(page);

    await expect(
      strategyTable(page).getByRole("cell", { name: "Profit", exact: true })
    ).toBeVisible({ timeout: 15_000 });

    // Every strategy appears as its own column.
    for (const strategy of [
      "Wholesale",
      "Fix & Flip",
      "Buy & Hold",
      "BRRRR",
      "Seller Finance",
    ]) {
      await expect(
        strategyTable(page).getByRole("columnheader", { name: new RegExp(strategy) })
      ).toBeVisible();
    }

    // A recommendation, with its reasoning.
    await expect(page.getByText("Recommended", { exact: false }).first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "Why this ranking" })).toBeVisible();
  });

  test("shows a verdict, confidence and risks rather than a bare number", async ({ page }) => {
    await page.goto("/analyzer");
    await fillDealInputs(page);

    await expect(page.getByRole("heading", { name: "Deal score" })).toBeVisible({
      timeout: 15_000,
    });
    // Exact, because the inputs column also has a "Declared risks" heading.
    await expect(
      page.getByRole("heading", { name: "Risks", exact: true })
    ).toBeVisible();
    await expect(page.getByRole("heading", { name: "Missing information" })).toBeVisible();
    // Coverage is stated, so a partial score cannot masquerade as a full one.
    await expect(page.getByText(/Assessed on \d+% of the rubric/)).toBeVisible();
  });

  test("an unverified ARV forces human review despite a strong score", async ({ page }) => {
    await page.goto("/analyzer");
    // Priced to be very profitable, but with no evidence behind the value.
    await page.getByLabel("Purchase price", { exact: true }).fill("80000");
    await page.getByLabel("After-repair value (ARV)").fill("250000");
    await page.getByLabel("Rehab", { exact: true }).fill("30000");

    await expect(page.getByText("Human review").first()).toBeVisible({ timeout: 15_000 });
    // Exact: the banner above also contains the phrase.
    await expect(page.getByText("Unverified ARV", { exact: true })).toBeVisible();
  });

  test("recomputes when an assumption changes", async ({ page }) => {
    await page.goto("/analyzer");
    await fillDealInputs(page);

    const flipProfit = strategyTable(page)
      .getByRole("row", { name: /^Profit/ })
      .getByRole("cell")
      .nth(2);
    await expect(flipProfit).not.toHaveText("—", { timeout: 15_000 });
    const before = await flipProfit.textContent();

    // Doubling the rehab contingency must reduce flip profit.
    await page.getByLabel("Rehab contingency").fill("30");
    await expect(flipProfit).not.toHaveText(before ?? "", { timeout: 15_000 });
  });

  test("an assumption left alone is marked as a provisional default", async ({ page }) => {
    await page.goto("/analyzer");
    await fillDealInputs(page);
    await expect(page.getByText("default").first()).toBeVisible({ timeout: 15_000 });
  });

  test("says what it cannot compute instead of showing zeros", async ({ page }) => {
    await page.goto("/analyzer");
    await page.getByLabel("Purchase price", { exact: true }).fill("150000");

    await expect(page.getByRole("heading", { name: "Missing information" })).toBeVisible({
      timeout: 15_000,
    });
    await page.getByRole("button", { name: "Fix & Flip detail" }).click();
    await expect(page.getByText("This strategy cannot be evaluated yet.")).toBeVisible();
  });
});

test.describe("Property lifecycle", () => {
  test("create a property, analyze it, save, and reopen it", async ({ page }) => {
    // 1. Create.
    await page.goto("/properties/new");
    await page.getByLabel("Address *").fill(ADDRESS);
    await page.getByLabel("City").fill("Chattanooga");
    await page.getByLabel("State").fill("TN");
    await page.getByLabel("Bedrooms").fill("3");
    await page.getByLabel("Bathrooms").fill("2");
    await page.getByLabel("Square feet").fill("1450");
    await page.getByLabel("Year built").fill("1998");
    await page.getByRole("button", { name: "Create property" }).click();

    await expect(page.getByRole("heading", { name: ADDRESS })).toBeVisible({
      timeout: 15_000,
    });

    // 2. Underwrite it.
    await page.getByRole("button", { name: "Financials" }).click();
    await fillDealInputs(page);
    await expect(
      strategyTable(page).getByRole("cell", { name: "Profit", exact: true })
    ).toBeVisible({ timeout: 15_000 });

    // 3. Save with a reason, which is what the audit trail records.
    await page.getByLabel("Reason for this change").fill("Initial underwriting");
    await page.getByRole("button", { name: /Save analysis|Save changes/ }).click();
    await expect(page.getByText(/Saved\./)).toBeVisible({ timeout: 15_000 });

    // 4. The audit trail records the starting assumptions.
    await expect(
      page.getByRole("heading", { name: "Assumption audit trail" })
    ).toBeVisible({ timeout: 15_000 });

    // 5. Reopen from the properties list and find the saved analysis.
    await page.goto("/properties");
    await page.getByRole("link", { name: ADDRESS }).click();
    await expect(page.getByRole("heading", { name: "Saved analyses" })).toBeVisible({
      timeout: 15_000,
    });
    await page.getByRole("button", { name: "Strategies" }).click();
    await expect(page.getByRole("heading", { name: "Strategies compared" })).toBeVisible();
  });

  test("changing a saved assumption is recorded with both values", async ({ page }) => {
    await page.goto("/properties");
    await page.getByRole("link", { name: ADDRESS }).click();
    await page.getByRole("button", { name: "Financials" }).click();

    await expect(page.getByLabel("After-repair value (ARV)")).toHaveValue("250000", {
      timeout: 15_000,
    });

    await page.getByLabel("After-repair value (ARV)").fill("275000");
    await page.getByLabel("Reason for this change").fill("Two newer comps closed higher");
    await page.getByRole("button", { name: /Save changes|Save analysis/ }).click();

    await expect(page.getByText(/Saved\./)).toBeVisible({ timeout: 15_000 });
    const auditRow = page.getByRole("row", { name: /ARV.*250000.*275000/ });
    await expect(auditRow.first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("Two newer comps closed higher").first()).toBeVisible();
  });

  test("the AI analysis works with no provider configured", async ({ page }) => {
    await page.goto("/properties");
    await page.getByRole("link", { name: ADDRESS }).click();
    await page.getByRole("button", { name: "AI Analysis" }).click();

    await page.getByRole("button", { name: /Generate/ }).click();
    await expect(
      page.getByText("Composed deterministically from the engine's numbers")
    ).toBeVisible({ timeout: 30_000 });
    // The separation between computed and interpreted is stated on screen.
    await expect(page.getByText(/not by a language model/)).toBeVisible();
  });
});

test.describe("Navigation and honesty about what is not built", () => {
  test("the dashboard loads and links onward", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  });

  test("markets says it is not built rather than showing a mock", async ({ page }) => {
    await page.goto("/markets");
    await expect(page.getByText("Not built yet")).toBeVisible();
  });

  test("settings shows the buy box and which connections are missing", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
    await expect(page.getByText(/Provisional underwriting default/)).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByRole("heading", { name: "Connections" })).toBeVisible();
    await expect(page.getByText(/Atlas runs with none of these configured/)).toBeVisible();
  });
});

test.describe("Calibration layer", () => {
  test("capital efficiency is reported and shows its working", async ({ page }) => {
    await page.goto("/analyzer");
    await fillDealInputs(page);

    await expect(page.getByRole("heading", { name: /Capital efficiency/ })).toBeVisible({
      timeout: 15_000,
    });
    // It is labelled provisional, and stated as additive to the deal score.
    await expect(page.getByText("provisional").first()).toBeVisible();
    await expect(page.getByText(/does not change it/)).toBeVisible();

    // The working must be inspectable, or the metric is not checkable.
    await page.getByRole("button", { name: "How Fix & Flip was computed" }).click();
    await expect(page.getByText(/annualised return on capital/)).toBeVisible();
    await expect(page.getByRole("heading", { name: "Inputs used" })).toBeVisible();
  });

  test("affordability is unknown until an investor profile is set", async ({ page }) => {
    await page.goto("/analyzer");
    await fillDealInputs(page);
    await expect(page.getByRole("heading", { name: /Capital efficiency/ })).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText("not stated").first()).toBeVisible();
  });

  test("the investor profile saves and constrains affordability", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Investor profile" })).toBeVisible({
      timeout: 15_000,
    });
    // Stated as describing the investor, not the property.
    await expect(page.getByText(/describes you, not a property/)).toBeVisible();

    await page.getByLabel("Available capital").fill("20000");
    await page.getByLabel("Max per deal").fill("15000");
    await page.getByLabel("Risk tolerance").selectOption("conservative");
    await page.getByRole("button", { name: "Save settings" }).click();
    await expect(page.getByText(/Saved\./)).toBeVisible({ timeout: 15_000 });

    // It persists.
    await page.reload();
    await expect(page.getByLabel("Available capital")).toHaveValue("20000", {
      timeout: 15_000,
    });

    // And it now answers the affordability question on a deal.
    await page.goto("/analyzer");
    await fillDealInputs(page);
    await expect(page.getByText("Exceeds limit").first()).toBeVisible({ timeout: 15_000 });
  });
});
