"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { LoadingState, StatusPanel } from "@/components/feedback/status-panel";
import { AppShell } from "@/components/shell/app-shell";
import type { Role } from "@/lib/api/contracts";
import { ClientApiError } from "@/lib/api/client";
import { activeRoles } from "@/lib/auth/roles";
import { useSession } from "@/components/auth/session-provider";

export function ProtectedPage({ role, title, children }: { role: Role; title: string; children: ReactNode }) {
  const session = useSession();
  const router = useRouter();
  const status = session.error instanceof ClientApiError ? session.error.status : 500;
  const allowed = session.data ? activeRoles(session.data.access.roles).includes(role) : false;
  useEffect(() => {
    if (session.error && status === 401) router.replace("/login?reason=expired");
    else if (session.error && (status === 403 || status === 404)) router.replace("/unauthorized");
    else if (session.data && !allowed) router.replace("/unauthorized");
  }, [allowed, router, session.data, session.error, status]);
  if (session.isPending) return <LoadingState />;
  if (session.error) return <main className="mx-auto max-w-xl p-8"><StatusPanel tone="error">We could not load your workspace. <button className="font-bold underline" onClick={() => session.refetch()}>Retry</button></StatusPanel></main>;
  if (!session.data || !allowed) return <LoadingState label="Confirming access…" />;
  return <AppShell session={session.data} role={role} title={title}>{children}</AppShell>;
}
