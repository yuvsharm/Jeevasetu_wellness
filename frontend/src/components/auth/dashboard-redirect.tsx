"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { LoadingState, StatusPanel } from "@/components/feedback/status-panel";
import { ClientApiError } from "@/lib/api/client";
import { primaryRole, roleDestinations } from "@/lib/auth/roles";
import { useSession } from "@/components/auth/session-provider";

export function DashboardRedirect() {
  const session = useSession();
  const router = useRouter();
  const role = session.data ? primaryRole(session.data.access.roles) : null;
  useEffect(() => {
    if (role) router.replace(roleDestinations[role]);
    else if (session.error instanceof ClientApiError && session.error.status === 401) router.replace("/login?reason=expired");
    else if (session.error || (session.data && !role)) router.replace("/unauthorized");
  }, [role, router, session.data, session.error]);
  if (session.error) return <main className="mx-auto max-w-lg p-8"><StatusPanel tone="error">Your secure workspace could not be resolved.</StatusPanel></main>;
  return <LoadingState label="Opening your role workspace…" />;
}
