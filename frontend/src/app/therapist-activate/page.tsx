import { AuthCard } from "@/components/auth/auth-card";
import { PractitionerActivation } from "@/components/auth/practitioner-auth";

export default function TherapistActivatePage() {
  return <AuthCard title="Activate therapist account" description="Verify your registered mobile number and create your private password."><PractitionerActivation /></AuthCard>;
}
