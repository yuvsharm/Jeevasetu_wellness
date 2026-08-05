import { NextRequest, NextResponse } from "next/server";

import { sessionErrorResponse } from "@/lib/auth/route-response";
import { requireSameOrigin, setSessionCookies, updateProfile } from "@/lib/auth/server-session";

export async function PATCH(request: NextRequest) {
  try {
    requireSameOrigin(request);
    const result = await updateProfile(request, await request.json());
    const response = NextResponse.json(result.user);
    if (result.tokens) setSessionCookies(response, result.tokens);
    return response;
  } catch (error) {
    return sessionErrorResponse(error);
  }
}
