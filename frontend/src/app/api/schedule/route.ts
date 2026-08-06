import type { NextRequest } from "next/server";
import { appointmentApi } from "@/lib/appointments/server-api";

export function GET(request: NextRequest) { return appointmentApi(request, `/appointments/schedule/?${request.nextUrl.searchParams}`); }
export async function POST(request: NextRequest) { return appointmentApi(request, "/appointments/schedule/", { method:"POST", body:await request.text() }); }
