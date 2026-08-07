import { NextRequest } from "next/server";
import { practitionerApi } from "@/lib/practitioners/server-api";
export async function POST(request:NextRequest,{params}:{params:Promise<{id:string}>}){return practitionerApi(request,`/practitioners/applications/${(await params).id}/review/`,{method:"POST",body:await request.text()});}

