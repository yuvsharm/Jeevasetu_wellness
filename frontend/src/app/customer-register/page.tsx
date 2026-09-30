import { Suspense } from "react";

import { AuthCard } from "@/components/auth/auth-card";
import { CustomerRegistration } from "@/components/auth/customer-registration";

export default function CustomerRegisterPage() {
  return <AuthCard title="Customer registration" description="Verify your mobile once and create your secure NuriPain Ease customer profile."><Suspense fallback={null}><CustomerRegistration /></Suspense></AuthCard>;
}
