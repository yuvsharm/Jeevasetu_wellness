import { ProtectedPage } from "@/components/auth/protected-page";
import { CustomerDashboard } from "@/components/appointments/customer-dashboard";
import { CustomerVisitVerificationPanel } from "@/components/appointments/visit-verification-panels";

export default function CustomerPage() {
  return <ProtectedPage role="CUSTOMER" title="My appointments"><CustomerDashboard /><CustomerVisitVerificationPanel /></ProtectedPage>;
}
