import { NextRequest, NextResponse } from "next/server";

import { djangoEndpoints } from "@/lib/api/endpoints";
import { sessionErrorResponse } from "@/lib/auth/route-response";
import { publicPost, requireSameOrigin } from "@/lib/auth/server-session";

export async function POST(request: NextRequest) {
  try {
    requireSameOrigin(request);
    await publicPost(djangoEndpoints.forgotPassword, await request.json());
    return NextResponse.json(
      { detail: "If an eligible account exists, reset instructions are available." },
      { status: 202 },
    );
  } catch (error) {
    return sessionErrorResponse(error);
  }
}
