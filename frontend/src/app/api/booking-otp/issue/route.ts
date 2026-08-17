import { NextRequest } from "next/server";

import { appointmentApi } from "@/lib/appointments/server-api";

export async function POST(request: NextRequest) {
  return appointmentApi(request, "/appointments/booking-otp/issue/", { method: "POST", body: await request.text() }, false);
}
