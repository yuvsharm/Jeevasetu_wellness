import { ProtectedPage } from "@/components/auth/protected-page";
import { PractitionerVisitWorkflow } from "@/components/appointments/practitioner-visit-workflow";
import { PhysiotherapistVisitVerificationPanel } from "@/components/appointments/visit-verification-panels";
import { MyAvailability } from "@/components/availability/availability-management";
import { PhysiotherapistProfile } from "@/components/staff/staff-management";
import { OpenToWorkControl } from "@/components/practitioners/open-to-work";
import { PractitionerDashboardOverview } from "@/components/practitioners/practitioner-dashboard";

export default function PhysiotherapistPage() {
  return <ProtectedPage role="PHYSIOTHERAPIST" title="Practitioner Dashboard"><PractitionerDashboardOverview /><PhysiotherapistProfile /><OpenToWorkControl /><MyAvailability /><PractitionerVisitWorkflow /><PhysiotherapistVisitVerificationPanel /></ProtectedPage>;
}
