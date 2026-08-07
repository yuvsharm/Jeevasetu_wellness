import { ProtectedPage } from "@/components/auth/protected-page";
import { AssignedAppointments } from "@/components/appointments/operational-schedule";
import { PhysiotherapistVisitVerificationPanel } from "@/components/appointments/visit-verification-panels";
import { MyAvailability } from "@/components/availability/availability-management";
import { PhysiotherapistProfile } from "@/components/staff/staff-management";

export default function PhysiotherapistPage() {
  return <ProtectedPage role="PHYSIOTHERAPIST" title="Professional profile"><PhysiotherapistProfile /><MyAvailability /><PhysiotherapistVisitVerificationPanel /><AssignedAppointments /></ProtectedPage>;
}
