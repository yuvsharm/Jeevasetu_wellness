import {NextRequest} from "next/server";
import {practitionerApi} from "@/lib/practitioners/server-api";
export async function GET(request:NextRequest,{params}:{params:Promise<{id:string}>}){const {id}=await params;const response=await practitionerApi(request,`/practitioners/applications/${id}/profile-photo/`);response.headers.set("Cache-Control","private, no-store");return response}
