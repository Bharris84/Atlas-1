import { PageHeader } from "@/components/Shell";
import { PlannedFeature } from "@/components/States";

export default function ContactsPage() {
  return (
    <>
      <PageHeader
        title="Contacts"
        description="Buyers, contractors, agents, lenders and title companies."
      />
      <PlannedFeature
        title="Not built yet"
        description="Communications are already logged per property on the property page. A standalone contact record that spans properties comes with the CRM phase."
        planned={[
          "Cash buyer list with the criteria each buyer actually buys on",
          "Contractors and vendors with historical bid-to-actual variance",
          "Lenders and title companies, with terms actually obtained",
          "Matching a property to the buyers whose box it fits",
        ]}
      />
    </>
  );
}
