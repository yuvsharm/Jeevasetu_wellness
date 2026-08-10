import {NextRequest} from "next/server";
import {practitionerApi} from "@/lib/practitioners/server-api";
export async function POST(request:NextRequest,{params}:{params:Promise<{id:string}>}){return practitionerApi(request,`/practitioners/applications/me/${(await params).id}/profile-photo/`,{method:"POST",body:await request.arrayBuffer()});}
export function GET(request:NextRequest,{params}:{params:Promise<{id:string}>}){return params.then(({id})=>practitionerApi(request,`/practitioners/applications/me/${id}/profile-photo/`));}
export function DELETE(request:NextRequest,{params}:{params:Promise<{id:string}>}){return params.then(({id})=>practitionerApi(request,`/practitioners/applications/me/${id}/profile-photo/`,{method:"DELETE"}));}
