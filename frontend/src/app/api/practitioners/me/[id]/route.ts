import { NextRequest } from "next/server";
import { practitionerApi } from "@/lib/practitioners/server-api";
export async function PATCH(request:NextRequest,{params}:{params:Promise<{id:string}>}){return practitionerApi(request,`/practitioners/applications/me/${(await params).id}/`,{method:"PATCH",body:await request.text()});}

