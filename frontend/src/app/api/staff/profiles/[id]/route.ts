import { NextRequest } from "next/server";
import { staffApi } from "@/lib/staff/server-api";

export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) { return staffApi(request, `/staff/profiles/${(await params).id}/`); }
export async function PATCH(request: NextRequest, { params }: { params: Promise<{ id: string }> }) { return staffApi(request, `/staff/profiles/${(await params).id}/`, { method: "PATCH", body: await request.arrayBuffer() }); }
