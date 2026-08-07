import type {NextRequest} from "next/server"; import {appointmentApi} from "@/lib/appointments/server-api";
export function GET(request:NextRequest){return appointmentApi(request,"/availability/me/rules/")}
export async function POST(request:NextRequest){return appointmentApi(request,"/availability/me/rules/",{method:"POST",body:await request.text()})}
