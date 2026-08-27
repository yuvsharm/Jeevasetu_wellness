import { NextRequest, NextResponse } from "next/server";

import { customerRegister, requireSameOrigin, setSessionCookies } from "@/lib/auth/server-session";
import { sessionErrorResponse } from "@/lib/auth/route-response";

export async function POST(request: NextRequest) {
  try {
    requireSameOrigin(request);
    const result = await customerRegister(await request.json());
    const response = NextResponse.json(result.session, { status: 201 });
    setSessionCookies(response, result.tokens);
    return response;
  } catch (error) {
    return sessionErrorResponse(error, true);
  }
}
