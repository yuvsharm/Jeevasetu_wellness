import { AuthCard } from "@/components/auth/auth-card";
import { CustomerPasswordLogin } from "@/components/auth/customer-password-login";
import { Suspense } from "react";

export default function CustomerLoginPage() {
  return <AuthCard title="Customer sign in" description="Use your registered mobile number and password to manage appointments."><Suspense fallback={null}><CustomerPasswordLogin /></Suspense></AuthCard>;
}
