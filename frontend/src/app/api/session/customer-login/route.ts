import { NextRequest, NextResponse } from "next/server";
import { customerPasswordLogin, requireSameOrigin, setSessionCookies } from "@/lib/auth/server-session";
import { sessionErrorResponse } from "@/lib/auth/route-response";

export async function POST(request: NextRequest) {
  try {
    requireSameOrigin(request);
    const result = await customerPasswordLogin(await request.json());
    const response = NextResponse.json(result.session);
    setSessionCookies(response, result.tokens);
    return response;
  } catch (error) {
    return sessionErrorResponse(error, true);
  }
}
