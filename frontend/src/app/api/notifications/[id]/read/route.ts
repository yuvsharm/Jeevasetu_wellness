import { NextRequest } from "next/server";

import { appointmentApi } from "@/lib/appointments/server-api";

export function POST(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  return context.params.then(({ id }) => appointmentApi(
    request,
    `/notifications/${encodeURIComponent(id)}/read/${request.nextUrl.search}`,
    { method: "POST" },
  ));
}
