import { ProtectedPage } from "@/components/auth/protected-page";
import { CustomerRequests } from "@/components/appointments/customer-requests";
import { CustomerAppointments } from "@/components/appointments/operational-schedule";
import { CustomerVisitVerificationPanel } from "@/components/appointments/visit-verification-panels";

export default function CustomerPage() {
  return <ProtectedPage role="CUSTOMER" title="My appointments"><CustomerVisitVerificationPanel /><CustomerAppointments /><CustomerRequests /></ProtectedPage>;
}
