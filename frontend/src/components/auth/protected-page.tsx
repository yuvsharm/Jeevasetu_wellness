"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { LoadingState, StatusPanel } from "@/components/feedback/status-panel";
import { AppShell } from "@/components/shell/app-shell";
import type { Role, Session } from "@/lib/api/contracts";
import { ClientApiError } from "@/lib/api/client";
import { activeRoles } from "@/lib/auth/roles";
import { useSession } from "@/components/auth/session-provider";

export function ProtectedPage({ role, title, children }: { role: Role; title: string; children: ReactNode }) {
  const session = useSession();
  const router = useRouter();
  const { isPending: sessionPending, refetch: refetchSession } = session;
  const [confirmed, setConfirmed] = useState(false);
  const [confirmedSession, setConfirmedSession] = useState<Session | null>(null);
  const accessCheckStarted = useRef(false);
  const status = session.error instanceof ClientApiError ? session.error.status : 500;
  const currentSession = confirmedSession ?? session.data;
  const allowed = currentSession ? activeRoles(currentSession.access.roles).includes(role) : false;
  useEffect(() => {
    if (sessionPending || accessCheckStarted.current) return;
    accessCheckStarted.current = true;
    let active = true;
    void refetchSession().then((result) => {
      if (active && result.data) setConfirmedSession(result.data);
    }).finally(() => { if (active) setConfirmed(true); });
    return () => { active = false; };
  }, [refetchSession, sessionPending]);
  useEffect(() => {
    if (!confirmed) return;
    if (session.error && status === 401) router.replace("/login?reason=expired");
    else if (session.error && (status === 403 || status === 404)) router.replace("/unauthorized");
    else if (currentSession && !allowed) router.replace("/unauthorized");
  }, [allowed, confirmed, currentSession, router, session.error, status]);
  if (session.isPending || !confirmed || session.isFetching) return <LoadingState />;
  if (session.error) return <main className="mx-auto max-w-xl p-8"><StatusPanel tone="error">We could not load your workspace. <button className="font-bold underline" onClick={() => session.refetch()}>Retry</button></StatusPanel></main>;
  if (!currentSession || !allowed) return <LoadingState label="Confirming access…" />;
  return <AppShell session={currentSession} role={role} title={title}>{children}</AppShell>;
}
