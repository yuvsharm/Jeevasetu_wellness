import { NextRequest } from "next/server";
import { staffApi } from "@/lib/staff/server-api";

export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) { return staffApi(request, `/staff/profiles/${(await params).id}/status/`, { method: "POST", body: await request.text() }); }
