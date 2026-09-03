import {NextRequest} from "next/server";
import {staffApi} from "@/lib/staff/server-api";

export async function POST(request:NextRequest){return staffApi(request,"/staff/mobile-availability/",{method:"POST",body:await request.text()})}
