import type { QueryClient } from "@tanstack/react-query";

import type { Session } from "@/lib/api/contracts";

export const sessionQueryKey = ["session"] as const;

export async function establishAuthenticatedSession(queryClient: QueryClient, session: Session) {
  await queryClient.cancelQueries({ queryKey: sessionQueryKey });
  queryClient.setQueryData(sessionQueryKey, session);
}
