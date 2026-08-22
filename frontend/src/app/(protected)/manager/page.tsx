import { ProtectedPage } from "@/components/auth/protected-page";
import { ScheduleOperations } from "@/components/appointments/operational-schedule";
import { OperationsVisitVerificationPanel } from "@/components/appointments/visit-verification-panels";
import { OwnerRequests } from "@/components/appointments/owner-requests";
import { AvailabilityOperations } from "@/components/availability/availability-management";
import { PatientDirectory } from "@/components/patients/patient-management";
import { ManagerDashboard } from "@/components/staff/staff-management";
import { PractitionerReview } from "@/components/practitioners/manager-review";
import { PaymentOperations } from "@/components/appointments/payment-operations";
import { ManagerOperationsDashboard } from "@/components/appointments/manager-operations-dashboard";

export default function ManagerPage() {
  return <ProtectedPage role="MANAGER" title="Operations team"><ManagerOperationsDashboard /><OwnerRequests /><ScheduleOperations /><OperationsVisitVerificationPanel /><PractitionerReview /><ManagerDashboard /><AvailabilityOperations /><PaymentOperations /><PatientDirectory /></ProtectedPage>;
}
