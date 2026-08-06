import { NextRequest } from "next/server";

import { appointmentApi } from "@/lib/appointments/server-api";

export function GET(request: NextRequest) { return appointmentApi(request, "/appointments/mine/"); }
export async function POST(request: NextRequest) { return appointmentApi(request, "/appointments/requests/", { method: "POST", body: await request.text() }); }
