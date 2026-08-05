import { AuthCard } from "@/components/auth/auth-card";
import { ForgotPasswordForm } from "@/components/auth/auth-forms";

export default function ForgotPasswordPage() {
  return <AuthCard title="Reset your password" description="Enter your registered email or mobile number. We never disclose whether an account exists."><ForgotPasswordForm /></AuthCard>;
}
