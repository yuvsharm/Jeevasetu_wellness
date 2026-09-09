import { AuthCard } from "@/components/auth/auth-card";
import { AccountPasswordReset } from "@/components/auth/account-password-reset";

export default function ForgotPasswordPage() {
  return <AuthCard title="Reset your password" description="Verify your registered mobile number, then choose a new password."><Suspense fallback={null}><AccountPasswordReset /></Suspense></AuthCard>;
}
import { Suspense } from "react";
