import "server-only";

import type { NextRequest } from "next/server";

const API_BASE_URL = process.env.DJANGO_API_BASE_URL ?? "http://localhost:8000/api/v1";
const ORGANIZATION_SLUG = process.env.NEXT_PUBLIC_DEFAULT_ORGANIZATION_SLUG ?? "";

export async function appointmentApi(request: NextRequest, path: string, init?: RequestInit) {
  const access = request.cookies.get("jeevasetu_access")?.value;
  try {
    const response = await fetch(`${API_BASE_URL.replace(/\/$/, "")}${path}`, {
      ...init,
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        ...(ORGANIZATION_SLUG ? { "X-Organization-Slug": ORGANIZATION_SLUG } : {}),
        ...(access ? { Authorization: `Bearer ${access}` } : {}),
      },
    });
    return new Response(response.body, { status: response.status, headers: { "Content-Type": response.headers.get("Content-Type") ?? "application/json" } });
  } catch {
    return Response.json({ detail: "The appointment service is temporarily unavailable." }, { status: 503 });
  }
}
