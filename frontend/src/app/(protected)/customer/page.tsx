import { ProtectedPage } from "@/components/auth/protected-page";
import { CustomerRequests } from "@/components/appointments/customer-requests";
import { CustomerAppointments } from "@/components/appointments/operational-schedule";

export default function CustomerPage() {
  return <ProtectedPage role="CUSTOMER" title="My appointments"><CustomerAppointments /><CustomerRequests /></ProtectedPage>;
}
