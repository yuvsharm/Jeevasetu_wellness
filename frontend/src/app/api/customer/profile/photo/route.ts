import type {NextRequest} from "next/server";
import {patientApi} from "@/lib/patients/server-api";

export function GET(request:NextRequest){return patientApi(request,"/patients/me/photo/");}
export async function POST(request:NextRequest){return patientApi(request,"/patients/me/photo/",{method:"POST",body:await request.arrayBuffer()});}
export function DELETE(request:NextRequest){return patientApi(request,"/patients/me/photo/",{method:"DELETE"});}
