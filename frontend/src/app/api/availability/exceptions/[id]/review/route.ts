import type {NextRequest} from "next/server"; import {appointmentApi} from "@/lib/appointments/server-api";
export async function POST(request:NextRequest,{params}:{params:Promise<{id:string}>}){return appointmentApi(request,`/availability/exceptions/${(await params).id}/review/`,{method:"POST",body:await request.text()})}
