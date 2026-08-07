import {NextRequest} from "next/server";
import {practitionerApi} from "@/lib/practitioners/server-api";
export async function POST(request:NextRequest,{params}:{params:Promise<{id:string}>}){return practitionerApi(request,`/practitioners/documents/${(await params).id}/verify/`,{method:"POST",body:await request.text()});}

