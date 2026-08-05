"use client";

import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { createContext, useContext } from "react";

import type { Session } from "@/lib/api/contracts";
import { requestJson } from "@/lib/api/client";
import { sessionEndpoints } from "@/lib/api/endpoints";

const SessionContext = createContext<ReturnType<typeof useSessionQuery> | null>(null);

function useSessionQuery() {
  return useQuery({
    queryKey: ["session"],
    queryFn: () => requestJson<Session>(sessionEndpoints.me),
    staleTime: 30_000,
    retry: false,
  });
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const query = useSessionQuery();
  return <SessionContext.Provider value={query}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession must be used inside SessionProvider");
  return value;
}
