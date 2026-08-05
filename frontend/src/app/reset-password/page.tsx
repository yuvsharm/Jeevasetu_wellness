import { Suspense } from "react";

import { AuthCard } from "@/components/auth/auth-card";
import { ResetPasswordForm } from "@/components/auth/auth-forms";
import { LoadingState } from "@/components/feedback/status-panel";

export default function ResetPasswordPage() {
  return <AuthCard title="Choose a new password" description="Use the reset details supplied through an approved channel."><Suspense fallback={<LoadingState label="Preparing reset form…" />}><ResetPasswordForm /></Suspense></AuthCard>;
}
