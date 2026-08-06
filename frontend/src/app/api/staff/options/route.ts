import { NextRequest } from "next/server";
import { staffApi } from "@/lib/staff/server-api";

export function GET(request: NextRequest) { return staffApi(request, "/staff/options/"); }
