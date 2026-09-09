import {NextRequest} from "next/server";
import {staffApi} from "@/lib/staff/server-api";
export async function GET(request:NextRequest,{params}:{params:Promise<{id:string}>}) {
 const response=await staffApi(request,`/staff/profiles/${(await params).id}/photo/`);
 response.headers.set("Cache-Control","private, no-store");
 response.headers.set("X-Content-Type-Options","nosniff");
 return response;
}
