import { NextRequest } from "next/server";
import { practitionerApi } from "@/lib/practitioners/server-api";
export async function POST(request:NextRequest){return practitionerApi(request,"/practitioners/me/open-to-work/",{method:"POST",body:await request.text()});}

