import {NextRequest} from "next/server";
import {practitionerApi} from "@/lib/practitioners/server-api";
export async function POST(request:NextRequest){const response=await practitionerApi(request,"/practitioners/dob-preview/",{method:"POST",body:await request.arrayBuffer()},false);response.headers.set("Cache-Control","private, no-store");return response;}
