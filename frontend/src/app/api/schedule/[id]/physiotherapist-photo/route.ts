import type { NextRequest } from "next/server";
import { appointmentApi } from "@/lib/appointments/server-api";

export function GET(request: NextRequest, {params}:{params:Promise<{id:string}>}) { return params.then(({id}) => appointmentApi(request, `/appointments/schedule/${id}/physiotherapist-photo/`)); }
