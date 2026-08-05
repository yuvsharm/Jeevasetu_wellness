import "server-only";

import { NextResponse } from "next/server";

import { SessionError, clearSessionCookies } from "@/lib/auth/server-session";

export function sessionErrorResponse(error: unknown, clear = false) {
  const known = error instanceof SessionError;
  const response = NextResponse.json(
    {
      detail: known ? error.detail : "The service is temporarily unavailable.",
      ...(known && error.fieldErrors ? { fieldErrors: error.fieldErrors } : {}),
    },
    { status: known ? error.status : 500 },
  );
  if (clear || (known && error.status === 401)) clearSessionCookies(response);
  return response;
}
