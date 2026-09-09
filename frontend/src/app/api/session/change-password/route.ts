import {NextRequest} from "next/server";
import {practitionerApi} from "@/lib/practitioners/server-api";
import {requireSameOrigin} from "@/lib/auth/server-session";
import {sessionErrorResponse} from "@/lib/auth/route-response";
export async function POST(request:NextRequest){try{requireSameOrigin(request);return practitionerApi(request,"/auth/password/change/",{method:"POST",body:await request.text()})}catch(error){return sessionErrorResponse(error)}}
