import { NextRequest } from "next/server";

import { appointmentApi } from "@/lib/appointments/server-api";

export async function GET(request: NextRequest, { params }: { params: Promise<{ clinicId: string }> }) {
  return appointmentApi(request, `/availability/operating-hours/${(await params).clinicId}/`);
}

export async function PUT(request: NextRequest, { params }: { params: Promise<{ clinicId: string }> }) {
  return appointmentApi(request, `/availability/operating-hours/${(await params).clinicId}/`, {
    method: "PUT",
    body: await request.text(),
  });
}
