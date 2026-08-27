import { AuthCard } from "@/components/auth/auth-card";
import { CustomerOtpLogin } from "@/components/auth/customer-otp-login";
import { Suspense } from "react";

export default function CustomerLoginPage() {
  return <AuthCard title="Customer sign in" description="Use your registered mobile number to securely manage appointments."><Suspense fallback={null}><CustomerOtpLogin /></Suspense></AuthCard>;
}
