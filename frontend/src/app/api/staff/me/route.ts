import { NextRequest } from "next/server";
import { staffApi } from "@/lib/staff/server-api";

export function GET(request: NextRequest) { return staffApi(request, "/staff/me/"); }
export async function PATCH(request: NextRequest) { return staffApi(request, "/staff/me/", { method: "PATCH", body: await request.arrayBuffer() }); }
