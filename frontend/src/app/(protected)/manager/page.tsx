import { ProtectedPage } from "@/components/auth/protected-page";
import { DashboardShell } from "@/components/dashboard/dashboard-shell";

export default function ManagerPage() {
  return <ProtectedPage role="MANAGER" title="Manager dashboard"><DashboardShell role="MANAGER" /></ProtectedPage>;
}
