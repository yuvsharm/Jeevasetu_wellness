import { NextRequest } from "next/server";
import { appointmentApi } from "@/lib/appointments/server-api";
export async function POST(request:NextRequest,{params}:{params:Promise<{id:string}>}){return appointmentApi(request,`/appointments/reviews/operations/${(await params).id}/moderate/`,{method:"POST",body:await request.text()})}
