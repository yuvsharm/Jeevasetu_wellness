import { ProtectedPage } from "@/components/auth/protected-page";
import { PhysiotherapistProfile } from "@/components/staff/staff-management";

export default function PhysiotherapistPage() {
  return <ProtectedPage role="PHYSIOTHERAPIST" title="Professional profile"><PhysiotherapistProfile /></ProtectedPage>;
}
