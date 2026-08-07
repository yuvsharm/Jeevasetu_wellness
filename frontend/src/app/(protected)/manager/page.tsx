import { ProtectedPage } from "@/components/auth/protected-page";
import { ScheduleOperations } from "@/components/appointments/operational-schedule";
import { OperationsVisitVerificationPanel } from "@/components/appointments/visit-verification-panels";
import { OwnerRequests } from "@/components/appointments/owner-requests";
import { AvailabilityOperations } from "@/components/availability/availability-management";
import { PatientDirectory } from "@/components/patients/patient-management";
import { ManagerDashboard } from "@/components/staff/staff-management";
import { PractitionerReview } from "@/components/practitioners/manager-review";

export default function ManagerPage() {
  return <ProtectedPage role="MANAGER" title="Operations team"><ManagerDashboard /><PractitionerReview /><OwnerRequests /><OperationsVisitVerificationPanel /><ScheduleOperations /><AvailabilityOperations /><PatientDirectory /></ProtectedPage>;
}
