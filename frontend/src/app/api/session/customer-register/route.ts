import { NextRequest, NextResponse } from "next/server";

import { clearSessionCookies, customerRegister, requireSameOrigin } from "@/lib/auth/server-session";
import { sessionErrorResponse } from "@/lib/auth/route-response";

export async function POST(request: NextRequest) {
  try {
    requireSameOrigin(request);
    const result = await customerRegister(await request.json());
    const response = NextResponse.json(result.session, { status: 201 });
    // Registration creates the account but intentionally does not sign the customer in.
    // Clearing any pre-existing staff/customer session keeps both login journeys separate.
    clearSessionCookies(response);
    return response;
  } catch (error) {
    return sessionErrorResponse(error, true);
  }
}
