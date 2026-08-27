import { Suspense } from "react";

import { AuthCard } from "@/components/auth/auth-card";
import { CustomerPasswordReset } from "@/components/auth/customer-password-reset";

export default function CustomerForgotPasswordPage() {
  return <AuthCard title="Reset customer password" description="Verify your registered mobile number, then choose a new password."><Suspense fallback={null}><CustomerPasswordReset /></Suspense></AuthCard>;
}
