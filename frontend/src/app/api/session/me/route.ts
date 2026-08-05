import { NextRequest, NextResponse } from "next/server";

import { sessionErrorResponse } from "@/lib/auth/route-response";
import { currentSession, setSessionCookies } from "@/lib/auth/server-session";

export async function GET(request: NextRequest) {
  try {
    const result = await currentSession(request);
    const response = NextResponse.json(result.session);
    if (result.tokens) setSessionCookies(response, result.tokens);
    return response;
  } catch (error) {
    return sessionErrorResponse(error, true);
  }
}
