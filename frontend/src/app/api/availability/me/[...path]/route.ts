import {NextRequest} from "next/server";
import {practitionerApi} from "@/lib/practitioners/server-api";
import {requireSameOrigin} from "@/lib/auth/server-session";
import {sessionErrorResponse} from "@/lib/auth/route-response";
type Context={params:Promise<{path?:string[]}>};
async function forward(request:NextRequest,context:Context){
 try {if(!["GET","HEAD"].includes(request.method))requireSameOrigin(request);
 const {path=[]}=await context.params;
 return practitionerApi(request,"/availability/me/"+(path.length?path.map(encodeURIComponent).join("/")+"/":"")+request.nextUrl.search,{method:request.method,...(["GET","HEAD"].includes(request.method)?{}:{body:await request.arrayBuffer()})});
 }catch(error){return sessionErrorResponse(error)}
}
export const GET=forward;export const POST=forward;export const PATCH=forward;export const DELETE=forward;
