import { NextRequest } from "next/server";
import { practitionerApi } from "@/lib/practitioners/server-api";

export async function DELETE(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  return practitionerApi(request, `/practitioners/competencies/${(await params).id}/`, { method: "DELETE" });
}
