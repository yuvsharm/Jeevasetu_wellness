import type { NextRequest } from "next/server";
import { appointmentApi } from "@/lib/appointments/server-api";
export function GET(request: NextRequest) { return appointmentApi(request, "/patients/family/"); }
export async function POST(request: NextRequest) { return appointmentApi(request, "/patients/family/", { method: "POST", body: await request.text(), headers: { "Content-Type": "application/json" } }); }
