import type { NextRequest } from "next/server";
import { patientApi } from "@/lib/patients/server-api";

export async function POST(request: NextRequest, { params }: { params: Promise<{id:string}> }) { return patientApi(request, `/patients/${(await params).id}/status/`, { method:"POST", body:await request.text() }); }
