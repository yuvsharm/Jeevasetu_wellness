import type { NextRequest } from "next/server";
import { patientApi } from "@/lib/patients/server-api";

export async function GET(request: NextRequest, { params }: { params: Promise<{id:string}> }) { return patientApi(request, `/patients/${(await params).id}/`); }
export async function PATCH(request: NextRequest, { params }: { params: Promise<{id:string}> }) { return patientApi(request, `/patients/${(await params).id}/`, { method:"PATCH", body:await request.arrayBuffer() }); }
