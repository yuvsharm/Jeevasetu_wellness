import { NextRequest, NextResponse } from "next/server";
import { customerOtpLogin, requireSameOrigin, setSessionCookies } from "@/lib/auth/server-session";
import { sessionErrorResponse } from "@/lib/auth/route-response";

export async function POST(request: NextRequest) {
  try {
    requireSameOrigin(request);
    const result = await customerOtpLogin(await request.json());
    const response = NextResponse.json(result.session);
    setSessionCookies(response, result.tokens);
    return response;
  } catch (error) {
    return sessionErrorResponse(error, true);
  }
}
