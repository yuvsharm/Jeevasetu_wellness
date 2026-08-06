import { ProtectedPage } from "@/components/auth/protected-page";
import { CustomerRequests } from "@/components/appointments/customer-requests";

export default function CustomerPage() {
  return <ProtectedPage role="CUSTOMER" title="My appointment requests"><CustomerRequests /></ProtectedPage>;
}
