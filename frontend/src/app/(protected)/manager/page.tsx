import { ProtectedPage } from "@/components/auth/protected-page";
import { ScheduleOperations } from "@/components/appointments/operational-schedule";
import { AvailabilityOperations } from "@/components/availability/availability-management";
import { PatientDirectory } from "@/components/patients/patient-management";
import { ManagerDashboard } from "@/components/staff/staff-management";

export default function ManagerPage() {
  return <ProtectedPage role="MANAGER" title="Operations team"><ManagerDashboard /><ScheduleOperations /><AvailabilityOperations /><PatientDirectory /></ProtectedPage>;
}
