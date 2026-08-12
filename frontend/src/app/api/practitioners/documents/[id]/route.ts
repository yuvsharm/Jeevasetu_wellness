import {NextRequest} from "next/server";
import {practitionerApi} from "@/lib/practitioners/server-api";
export function GET(request:NextRequest,{params}:{params:Promise<{id:string}>}){return params.then(({id})=>practitionerApi(request,`/practitioners/documents/${id}/`));}
export function DELETE(request:NextRequest,{params}:{params:Promise<{id:string}>}){return params.then(({id})=>practitionerApi(request,`/practitioners/documents/${id}/`,{method:"DELETE"}));}

