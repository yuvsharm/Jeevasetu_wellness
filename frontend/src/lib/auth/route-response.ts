import "server-only";

import { NextResponse } from "next/server";

import { SessionError, clearSessionCookies } from "@/lib/auth/server-session";

export function sessionErrorResponse(error: unknown, clear = false) {
  const known = error instanceof SessionError;
  const response = NextResponse.json(
    {
      detail: known ? error.detail : "The service is temporarily unavailable.",
      ...(known && error.fieldErrors ? { fieldErrors: error.fieldErrors } : {}),
      ...(known && error.retryAfter ? { retry_after: error.retryAfter } : {}),
    },
    { status: known ? error.status : 500 },
  );
  if (known && error.retryAfter) response.headers.set("Retry-After", String(error.retryAfter));
  if (clear || (known && error.status === 401)) clearSessionCookies(response);
  return response;
}
