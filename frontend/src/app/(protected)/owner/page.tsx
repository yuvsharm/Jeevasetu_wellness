import { ProtectedPage } from "@/components/auth/protected-page";
import { OwnerRequests } from "@/components/appointments/owner-requests";
import { ScheduleOperations } from "@/components/appointments/operational-schedule";
import { AvailabilityOperations } from "@/components/availability/availability-management";
import { PatientDirectory } from "@/components/patients/patient-management";
import { StaffDirectory } from "@/components/staff/staff-management";

export default function OwnerPage() {
  return <ProtectedPage role="OWNER" title="Owner operations"><OwnerRequests /><ScheduleOperations /><AvailabilityOperations /><StaffDirectory allowManagers /><PatientDirectory /></ProtectedPage>;
}
