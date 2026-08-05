import { ProtectedPage } from "@/components/auth/protected-page";
import { DashboardShell } from "@/components/dashboard/dashboard-shell";

export default function OwnerPage() {
  return <ProtectedPage role="OWNER" title="Owner overview"><DashboardShell role="OWNER" /></ProtectedPage>;
}
