import { NextRequest } from "next/server";

import { appointmentApi } from "@/lib/appointments/server-api";

export async function POST(request: NextRequest) {
  return appointmentApi(request, "/appointments/quick-requests/", { method: "POST", body: await request.text() }, false);
}
