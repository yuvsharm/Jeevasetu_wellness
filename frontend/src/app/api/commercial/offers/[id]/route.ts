import { NextRequest } from "next/server"; import { appointmentApi } from "@/lib/appointments/server-api";
export async function PATCH(request:NextRequest,{params}:{params:Promise<{id:string}>}){return appointmentApi(request,`/appointments/commercial/offers/${(await params).id}/`,{method:"PATCH",body:await request.text()})}
export async function DELETE(request:NextRequest,{params}:{params:Promise<{id:string}>}){return appointmentApi(request,`/appointments/commercial/offers/${(await params).id}/`,{method:"DELETE"})}
