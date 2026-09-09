import {NextRequest} from "next/server";
import {practitionerApi} from "@/lib/practitioners/server-api";
export async function GET(request:NextRequest,{params}:{params:Promise<{id:string}>}){const response=await practitionerApi(request,`/practitioners/public/${(await params).id}/photo/`,undefined,false);response.headers.set("Cache-Control","no-store");return response;}
