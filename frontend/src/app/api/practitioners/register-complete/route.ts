import {NextRequest} from "next/server";
import {practitionerApi} from "@/lib/practitioners/server-api";
import {requireSameOrigin} from "@/lib/auth/server-session";
import {sessionErrorResponse} from "@/lib/auth/route-response";
export async function POST(request:NextRequest){try{requireSameOrigin(request);const response=await practitionerApi(request,"/practitioners/register-complete/",{method:"POST",body:await request.arrayBuffer()},false);response.headers.set("Cache-Control","private, no-store");return response}catch(error){return sessionErrorResponse(error,true)}}
