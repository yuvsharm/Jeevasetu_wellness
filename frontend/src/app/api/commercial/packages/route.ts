import { NextRequest } from "next/server"; import { appointmentApi } from "@/lib/appointments/server-api";
export function GET(request:NextRequest){return appointmentApi(request,"/appointments/commercial/packages/")}
export async function POST(request:NextRequest){return appointmentApi(request,"/appointments/commercial/packages/",{method:"POST",body:await request.text()})}
