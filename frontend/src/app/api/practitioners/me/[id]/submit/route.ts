import { NextRequest } from "next/server";
import { practitionerApi } from "@/lib/practitioners/server-api";
export async function POST(request:NextRequest,{params}:{params:Promise<{id:string}>}){return practitionerApi(request,`/practitioners/applications/me/${(await params).id}/submit/`,{method:"POST",body:"{}"});}

