import { NextRequest, NextResponse } from "next/server";

import { sessionErrorResponse } from "@/lib/auth/route-response";
import { clearSessionCookies, publicPost, requireSameOrigin } from "@/lib/auth/server-session";

export async function POST(request: NextRequest) {
  try {
    requireSameOrigin(request);
    const result = await publicPost<{ detail: string; activated: boolean }>(
      "/auth/practitioner-register/",
      await request.json(),
    );
    const response = NextResponse.json(result, { status: result.activated ? 200 : 201 });
    clearSessionCookies(response);
    return response;
  } catch (error) {
    return sessionErrorResponse(error, true);
  }
}
