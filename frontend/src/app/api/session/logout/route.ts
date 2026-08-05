import { NextRequest, NextResponse } from "next/server";

import { sessionErrorResponse } from "@/lib/auth/route-response";
import { clearSessionCookies, requireSameOrigin, revokeSession } from "@/lib/auth/server-session";

export async function POST(request: NextRequest) {
  try {
    requireSameOrigin(request);
    await revokeSession(request);
    const response = new NextResponse(null, { status: 204 });
    clearSessionCookies(response);
    return response;
  } catch (error) {
    const response = sessionErrorResponse(error, true);
    clearSessionCookies(response);
    return response;
  }
}
