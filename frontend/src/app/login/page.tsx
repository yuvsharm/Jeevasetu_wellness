import { AuthCard } from "@/components/auth/auth-card";
import { LoginForm } from "@/components/auth/auth-forms";

export default function LoginPage() {
  return <AuthCard title="Welcome back" description="Sign in to your secure JeevaSetu workspace."><LoginForm /></AuthCard>;
}
