import type { NextRequest } from "next/server";

import { appointmentApi } from "@/lib/appointments/server-api";

function path(id: string) {
  return `/appointments/schedule/assigned-to-me/${id}/visit-verification/`;
}

export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  return appointmentApi(request, path((await params).id));
}

export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  return appointmentApi(request, path((await params).id), {
    method: "POST",
    body: await request.text(),
  });
}
