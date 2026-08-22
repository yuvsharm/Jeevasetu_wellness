import { AuthCard } from "@/components/auth/auth-card";
import { CustomerOtpLogin } from "@/components/auth/customer-otp-login";

export default function CustomerLoginPage() {
  return <AuthCard title="Customer sign in" description="Use your verified mobile number to securely manage appointments."><CustomerOtpLogin /></AuthCard>;
}
