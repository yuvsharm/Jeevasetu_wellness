import { AuthCard } from "@/components/auth/auth-card";
import { RegistrationForm } from "@/components/auth/auth-forms";

export default function RegisterPage() {
  return <AuthCard title="Create your account" description="Register your identity. Organization access and roles remain controlled by JeevaSetu policy."><RegistrationForm /></AuthCard>;
}
