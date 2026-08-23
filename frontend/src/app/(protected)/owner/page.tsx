import { ProtectedPage } from "@/components/auth/protected-page";
import { OwnerRequests } from "@/components/appointments/owner-requests";
import { ScheduleOperations } from "@/components/appointments/operational-schedule";
import { OperationsVisitVerificationPanel } from "@/components/appointments/visit-verification-panels";
import { AvailabilityOperations } from "@/components/availability/availability-management";
import { PatientDirectory } from "@/components/patients/patient-management";
import { StaffDirectory } from "@/components/staff/staff-management";
import { PractitionerReview } from "@/components/practitioners/manager-review";
import { PaymentOperations } from "@/components/appointments/payment-operations";
import { ReviewModerationPanel } from "@/components/appointments/review-panels";
import { CommercialManagement } from "@/components/appointments/commercial-management";

export default function OwnerPage() {
  return <ProtectedPage role="OWNER" title="Owner operations"><CommercialManagement /><ReviewModerationPanel /><PractitionerReview /><OwnerRequests /><OperationsVisitVerificationPanel /><ScheduleOperations /><PaymentOperations /><AvailabilityOperations /><StaffDirectory allowManagers /><PatientDirectory /></ProtectedPage>;
}
