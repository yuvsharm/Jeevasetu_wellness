import { NextRequest } from "next/server";
import { staffApi } from "@/lib/staff/server-api";

export async function PATCH(request: NextRequest) { return staffApi(request, "/staff/me/availability/", { method: "PATCH", body: await request.text() }); }
