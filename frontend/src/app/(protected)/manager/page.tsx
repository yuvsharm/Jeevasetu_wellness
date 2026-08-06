import { ProtectedPage } from "@/components/auth/protected-page";
import { PatientDirectory } from "@/components/patients/patient-management";
import { ManagerDashboard } from "@/components/staff/staff-management";

export default function ManagerPage() {
  return <ProtectedPage role="MANAGER" title="Operations team"><ManagerDashboard /><PatientDirectory /></ProtectedPage>;
}
