import Link from "next/link";

import { AuthCard } from "@/components/auth/auth-card";

function safeReturnTo(value?: string) {
  return value?.startsWith("/") && !value.startsWith("//") ? value : "/book-appointment";
}

export default async function CustomerAccessPage({ searchParams }: { searchParams: Promise<{ returnTo?: string }> }) {
  const returnTo = safeReturnTo((await searchParams).returnTo);
  return (
    <AuthCard title="Continue as a customer" description="Register once or sign in with your verified mobile number. You will return to your selected booking.">
      <div className="grid gap-4">
        <Link className="button-primary" href={`/customer-register?returnTo=${encodeURIComponent(returnTo)}`}>Register as a customer</Link>
        <Link className="button-secondary" href={`/customer-login?returnTo=${encodeURIComponent(returnTo)}`}>Customer Login</Link>
        <Link className="text-center text-sm font-semibold text-emerald-800" href="/login">Staff Login</Link>
      </div>
    </AuthCard>
  );
}
