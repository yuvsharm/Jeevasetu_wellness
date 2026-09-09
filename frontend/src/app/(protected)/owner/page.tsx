import { ProtectedPage } from "@/components/auth/protected-page";
import { OwnerRequests } from "@/components/appointments/owner-requests";
import { ScheduleOperations } from "@/components/appointments/operational-schedule";
import { OperationsVisitVerificationPanel } from "@/components/appointments/visit-verification-panels";
import { OperatingHoursManagement } from "@/components/availability/operating-hours-management";
import { PatientDirectory } from "@/components/patients/patient-management";
import { StaffDirectory } from "@/components/staff/staff-management";
import { PractitionerReview } from "@/components/practitioners/manager-review";
import { PaymentOperations } from "@/components/appointments/payment-operations";
import { ReviewModerationPanel } from "@/components/appointments/review-panels";
import { CommercialManagement } from "@/components/appointments/commercial-management";
import { OwnerAnalyticsDashboard } from "@/components/analytics/owner-analytics-dashboard";
import { TherapyManagement } from "@/components/appointments/therapy-management";

export default function OwnerPage() {
  const sectionClass = "scroll-mt-24 focus:outline-none";
  return <ProtectedPage role="OWNER" title="Owner operations">
    <div id="business-analytics" tabIndex={-1} className={sectionClass}><OwnerAnalyticsDashboard /></div>
    <TherapyManagement />
    <CommercialManagement />
    <div id="customer-reviews" tabIndex={-1} className={sectionClass}><ReviewModerationPanel /></div>
    <div id="practitioner-applications" tabIndex={-1} className={sectionClass}><PractitionerReview /></div>
    <div id="appointment-requests" tabIndex={-1} className={sectionClass}><OwnerRequests /></div>
    <div id="visit-verification" tabIndex={-1} className={sectionClass}><OperationsVisitVerificationPanel /></div>
    <div id="appointment-schedule" tabIndex={-1} className={sectionClass}><ScheduleOperations /></div>
    <div id="payments" tabIndex={-1} className={sectionClass}><PaymentOperations /></div>
    <OperatingHoursManagement />
    <div id="staff-management" tabIndex={-1} className={sectionClass}><StaffDirectory allowManagers /></div>
    <div id="patients" tabIndex={-1} className={sectionClass}><PatientDirectory /></div>
  </ProtectedPage>;
}
