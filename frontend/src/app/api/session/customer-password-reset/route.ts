import { NextRequest, NextResponse } from "next/server";

import { customerPasswordReset, requireSameOrigin } from "@/lib/auth/server-session";
import { sessionErrorResponse } from "@/lib/auth/route-response";

export async function POST(request: NextRequest) {
  try {
    requireSameOrigin(request);
    return NextResponse.json(await customerPasswordReset(await request.json()));
  } catch (error) {
    return sessionErrorResponse(error, true);
  }
}
