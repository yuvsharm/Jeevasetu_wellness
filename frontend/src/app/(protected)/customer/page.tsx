import { ProtectedPage } from "@/components/auth/protected-page";
import { CustomerDashboard } from "@/components/appointments/customer-dashboard";

export default function CustomerPage() {
  return <ProtectedPage role="CUSTOMER" title="My appointments"><CustomerDashboard /></ProtectedPage>;
}
