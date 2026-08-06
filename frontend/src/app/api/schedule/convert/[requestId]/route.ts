import type { NextRequest } from "next/server";
import { appointmentApi } from "@/lib/appointments/server-api";

export async function POST(request: NextRequest, {params}:{params:Promise<{requestId:string}>}) { return appointmentApi(request, `/appointments/schedule/from-request/${(await params).requestId}/`, {method:"POST",body:await request.text()}); }
