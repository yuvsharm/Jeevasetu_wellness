import type { NextRequest } from "next/server";

import { appointmentApi } from "@/lib/appointments/server-api";

export function GET(request: NextRequest) {
  return appointmentApi(request, "/appointments/schedule/physiotherapist-workload/");
}
