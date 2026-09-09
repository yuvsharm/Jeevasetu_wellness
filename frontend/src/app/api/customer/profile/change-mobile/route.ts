import type {NextRequest} from "next/server";
import {patientApi} from "@/lib/patients/server-api";

export async function POST(request:NextRequest){return patientApi(request,"/patients/me/change-mobile/",{method:"POST",body:await request.text()});}
