import {NextRequest,NextResponse} from "next/server";
import {publicPost,requireSameOrigin,clearSessionCookies} from "@/lib/auth/server-session";
import {sessionErrorResponse} from "@/lib/auth/route-response";
export async function POST(request:NextRequest){try{requireSameOrigin(request);const result=await publicPost("/auth/account-password-reset/",await request.json());const response=NextResponse.json(result);clearSessionCookies(response);return response}catch(error){return sessionErrorResponse(error,true)}}
