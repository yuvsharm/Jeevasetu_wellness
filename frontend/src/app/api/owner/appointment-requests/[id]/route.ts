import { NextRequest } from "next/server";

import { appointmentApi } from "@/lib/appointments/server-api";

export async function PATCH(request: NextRequest, context: { params: Promise<{ id: string }> }) { const { id } = await context.params; return appointmentApi(request, `/appointments/owner/${id}/`, { method: "PATCH", body: await request.text() }); }
