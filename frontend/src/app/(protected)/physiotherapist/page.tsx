import { ProtectedPage } from "@/components/auth/protected-page";
import { DashboardShell } from "@/components/dashboard/dashboard-shell";

export default function PhysiotherapistPage() {
  return <ProtectedPage role="PHYSIOTHERAPIST" title="Physiotherapist dashboard"><DashboardShell role="PHYSIOTHERAPIST" /></ProtectedPage>;
}
