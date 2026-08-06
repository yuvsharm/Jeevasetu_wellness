import { NextRequest } from "next/server";

import { appointmentApi } from "@/lib/appointments/server-api";

export async function POST(request: NextRequest, context: { params: Promise<{ id: string }> }) { const { id } = await context.params; return appointmentApi(request, `/appointments/mine/${id}/cancel/`, { method: "PATCH", body: "{}" }); }
