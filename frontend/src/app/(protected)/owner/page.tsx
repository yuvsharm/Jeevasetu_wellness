import { ProtectedPage } from "@/components/auth/protected-page";
import { OwnerRequests } from "@/components/appointments/owner-requests";
import { ScheduleOperations } from "@/components/appointments/operational-schedule";
import { OperationsVisitVerificationPanel } from "@/components/appointments/visit-verification-panels";
import { AvailabilityOperations } from "@/components/availability/availability-management";
import { OperatingHoursManagement } from "@/components/availability/operating-hours-management";
import { PatientDirectory } from "@/components/patients/patient-management";
import { StaffDirectory } from "@/components/staff/staff-management";
import { PractitionerReview } from "@/components/practitioners/manager-review";
import { PaymentOperations } from "@/components/appointments/payment-operations";
import { ReviewModerationPanel } from "@/components/appointments/review-panels";
import { CommercialManagement } from "@/components/appointments/commercial-management";
import { OwnerAnalyticsDashboard } from "@/components/analytics/owner-analytics-dashboard";

export default function OwnerPage() {
  return <ProtectedPage role="OWNER" title="Owner operations"><OwnerAnalyticsDashboard /><div id="operations"><CommercialManagement /><ReviewModerationPanel /><div id="practitioner-review"><PractitionerReview /></div><div id="owner-appointment-requests" tabIndex={-1} className="scroll-mt-24 focus:outline-none"><OwnerRequests /></div><OperationsVisitVerificationPanel /><div id="owner-appointment-schedule" tabIndex={-1} className="scroll-mt-24 focus:outline-none"><ScheduleOperations /></div><PaymentOperations /><OperatingHoursManagement /><div id="owner-staff" tabIndex={-1} className="scroll-mt-24 focus:outline-none"><StaffDirectory allowManagers /></div><AvailabilityOperations /><div id="owner-patients" tabIndex={-1} className="scroll-mt-24 focus:outline-none"><PatientDirectory /></div></div></ProtectedPage>;
}
