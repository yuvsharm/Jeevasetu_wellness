import type { NextRequest } from "next/server";
import { patientApi } from "@/lib/patients/server-api";

export async function GET(request: NextRequest) { return patientApi(request, `/patients/?${request.nextUrl.searchParams}`); }
export async function POST(request: NextRequest) { return patientApi(request, "/patients/", { method: "POST", body: await request.text() }); }
