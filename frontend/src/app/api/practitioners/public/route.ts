import { NextRequest } from "next/server";
import { practitionerApi } from "@/lib/practitioners/server-api";
export function GET(request:NextRequest){return practitionerApi(request,"/practitioners/public/",undefined,false);}

