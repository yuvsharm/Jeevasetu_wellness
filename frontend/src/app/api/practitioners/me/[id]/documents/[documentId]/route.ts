import { NextRequest } from "next/server";

import { practitionerApi } from "@/lib/practitioners/server-api";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string; documentId: string }> },
) {
  const { id, documentId } = await params;
  return practitionerApi(
    request,
    `/practitioners/applications/me/${id}/documents/${documentId}/`,
  );
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ id: string; documentId: string }> },
) {
  const { id, documentId } = await params;
  return practitionerApi(
    request,
    `/practitioners/applications/me/${id}/documents/${documentId}/`,
    { method: "DELETE" },
  );
}
