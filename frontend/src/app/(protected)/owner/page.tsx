import { ProtectedPage } from "@/components/auth/protected-page";
import { OwnerRequests } from "@/components/appointments/owner-requests";

export default function OwnerPage() {
  return <ProtectedPage role="OWNER" title="Appointment requests"><OwnerRequests /></ProtectedPage>;
}
