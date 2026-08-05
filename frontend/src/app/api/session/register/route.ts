import { NextRequest, NextResponse } from "next/server";

import type { UserSummary } from "@/lib/api/contracts";
import { djangoEndpoints } from "@/lib/api/endpoints";
import { sessionErrorResponse } from "@/lib/auth/route-response";
import { publicPost, requireSameOrigin } from "@/lib/auth/server-session";

export async function POST(request: NextRequest) {
  try {
    requireSameOrigin(request);
    return NextResponse.json(
      await publicPost<UserSummary>(djangoEndpoints.register, await request.json()),
      { status: 201 },
    );
  } catch (error) {
    return sessionErrorResponse(error);
  }
}
