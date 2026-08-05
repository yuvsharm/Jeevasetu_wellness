import { ProtectedPage } from "@/components/auth/protected-page";
import { DashboardShell } from "@/components/dashboard/dashboard-shell";

export default function CustomerPage() {
  return <ProtectedPage role="CUSTOMER" title="Customer dashboard"><DashboardShell role="CUSTOMER" /></ProtectedPage>;
}
