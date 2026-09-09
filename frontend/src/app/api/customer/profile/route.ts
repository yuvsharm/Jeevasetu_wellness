import type {NextRequest} from "next/server";
import {patientApi} from "@/lib/patients/server-api";

export function GET(request:NextRequest){return patientApi(request,"/patients/me/");}
export async function PATCH(request:NextRequest){return patientApi(request,"/patients/me/",{method:"PATCH",body:await request.text()});}
