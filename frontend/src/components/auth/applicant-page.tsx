"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { useSession } from "@/components/auth/session-provider";
import { LoadingState, StatusPanel } from "@/components/feedback/status-panel";
import { PublicShell } from "@/components/public/public-shell";
import { ClientApiError } from "@/lib/api/client";

export function ApplicantPage({ children }: { children: ReactNode }) {
  const session = useSession();
  const router = useRouter();
  const status = session.error instanceof ClientApiError ? session.error.status : 500;

  useEffect(() => {
    if (session.error && status === 401) {
      router.replace("/login?reason=expired&returnTo=%2Fpractitioner-application");
    } else if (session.error && (status === 403 || status === 404)) {
      router.replace("/unauthorized");
    }
  }, [router, session.error, status]);

  if (session.isPending) return <LoadingState label="Opening your application…" />;
  if (session.error) return <main className="mx-auto max-w-xl p-8"><StatusPanel tone="error">We could not load your application.</StatusPanel></main>;
  if (!session.data) return <LoadingState label="Confirming your identity…" />;

  return <PublicShell><main className="site-container section"><h1 className="mb-8 font-serif text-4xl text-[#103c27]">Practitioner enrollment</h1>{children}</main></PublicShell>;
}
