import { NextRequest, NextResponse } from "next/server";

import { sessionErrorResponse } from "@/lib/auth/route-response";
import { login, requireSameOrigin, setSessionCookies } from "@/lib/auth/server-session";

export async function POST(request: NextRequest) {
  try {
    requireSameOrigin(request);
    const result = await login(await request.json());
    const response = NextResponse.json(result.session);
    setSessionCookies(response, result.tokens);
    return response;
  } catch (error) {
    return sessionErrorResponse(error, true);
  }
}
