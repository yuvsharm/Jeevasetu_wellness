import { NextRequest } from "next/server";
import { staffApi } from "@/lib/staff/server-api";

export function GET(request: NextRequest) { return staffApi(request, `/staff/profiles/${request.nextUrl.search}`); }
export async function POST(request: NextRequest) { return staffApi(request, "/staff/profiles/", { method: "POST", body: await request.arrayBuffer() }); }
