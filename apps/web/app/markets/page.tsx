import { PageHeader } from "@/components/Shell";
import { PlannedFeature } from "@/components/States";

export default function MarketsPage() {
  return (
    <>
      <PageHeader
        title="Markets"
        description="Market intelligence is a later phase. Until it exists, Atlas excludes the Market category from the deal score rather than filling it with a guess."
      />
      <PlannedFeature
        title="Not built yet"
        description="Atlas is architected for nationwide coverage — no part of the codebase is specialised to a particular state. What is missing is the data, not the structure."
        planned={[
          "Median sale price, rent and days-on-market by ZIP and county",
          "Rent-to-price and appreciation trends over time",
          "Market scoring feeding the 15% Market weight in the deal score",
          "Automated discovery of markets that fit the buy box",
        ]}
      />
    </>
  );
}
