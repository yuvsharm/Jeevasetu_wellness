import { NextRequest, NextResponse } from "next/server";

import { djangoEndpoints } from "@/lib/api/endpoints";
import { sessionErrorResponse } from "@/lib/auth/route-response";
import { publicPost, requireSameOrigin } from "@/lib/auth/server-session";

export async function POST(request: NextRequest) {
  try {
    requireSameOrigin(request);
    return NextResponse.json(
      await publicPost(djangoEndpoints.resetPassword, await request.json()),
    );
  } catch (error) {
    return sessionErrorResponse(error);
  }
}
