import "server-only";
import type { NextRequest } from "next/server";

const API_BASE_URL = process.env.DJANGO_API_BASE_URL ?? "http://localhost:8000/api/v1";
const ORGANIZATION_SLUG = process.env.NEXT_PUBLIC_DEFAULT_ORGANIZATION_SLUG ?? "";

export async function practitionerApi(request: NextRequest, path: string, init?: RequestInit, authenticated = true) {
  const access = request.cookies.get("jeevasetu_access")?.value;
  if (authenticated && !access) return Response.json({detail:"Your session has expired."},{status:401});
  try {
    const response = await fetch(`${API_BASE_URL.replace(/\/$/, "")}${path}`, { ...init, cache:"no-store", headers:{ ...(request.headers.get("content-type") ? {"Content-Type":request.headers.get("content-type")!}:{}), "X-Organization-Slug":ORGANIZATION_SLUG, ...(access?{Authorization:`Bearer ${access}`}:{}) } });
    return new Response(response.body,{status:response.status,headers:{"Content-Type":response.headers.get("content-type")??"application/json","Content-Disposition":response.headers.get("content-disposition")??""}});
  } catch { return Response.json({detail:"The practitioner service is temporarily unavailable."},{status:503}); }
}

