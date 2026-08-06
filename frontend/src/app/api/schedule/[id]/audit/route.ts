import type { NextRequest } from "next/server";

import { appointmentApi } from "@/lib/appointments/server-api";

export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  return appointmentApi(request, `/appointments/schedule/${(await params).id}/audit/`);
}
