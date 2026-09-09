import { PageHeader } from "@/components/Shell";
import { PlannedFeature } from "@/components/States";

export default function ProjectsPage() {
  return (
    <>
      <PageHeader
        title="Projects"
        description="Rehab execution: estimated versus actual."
      />
      <PlannedFeature
        title="Partially built"
        description="Rehab projects can be recorded against a property through the API, including estimated versus actual cost and the resulting variance. The management interface is a later phase."
        planned={[
          "Scope of work broken down by trade",
          "Contractor assignment and draw schedule",
          "Estimated versus actual variance, fed back into rehab confidence",
          "Equipment and cleanup logistics handled in-house",
        ]}
      />
    </>
  );
}
