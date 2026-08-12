import "server-only";
import { NextRequest, NextResponse } from "next/server";

import { refreshSession, SessionError, setSessionCookies } from "@/lib/auth/server-session";

const API_BASE_URL = process.env.DJANGO_API_BASE_URL ?? "http://localhost:8000/api/v1";
const ORGANIZATION_SLUG = process.env.NEXT_PUBLIC_DEFAULT_ORGANIZATION_SLUG ?? "";

export async function appointmentApi(request: NextRequest, path: string, init?: RequestInit, authenticated = true) {
  let access = request.cookies.get("jeevasetu_access")?.value;
  try {
    const send = (token?: string) => fetch(`${API_BASE_URL.replace(/\/$/, "")}${path}`, { ...init, cache:"no-store", headers:{ ...(request.headers.get("content-type") ? {"Content-Type":request.headers.get("content-type")!}:{}), "X-Organization-Slug":ORGANIZATION_SLUG, ...(token?{Authorization:`Bearer ${token}`}:{}) } });
    let rotated = null;
    if (authenticated && !access) {
      const refresh = request.cookies.get("jeevasetu_refresh")?.value;
      if (!refresh) return Response.json({detail:"Your session has expired."},{status:401});
      rotated = await refreshSession(refresh);
      access = rotated.tokens.access;
    }
    let response = await send(access);
    if (authenticated && response.status === 401) {
      const refresh = request.cookies.get("jeevasetu_refresh")?.value;
      if (!refresh) return Response.json({detail:"Your session has expired."},{status:401});
      rotated = await refreshSession(refresh);
      access = rotated.tokens.access;
      response = await send(access);
    }
    const body = [204, 205, 304].includes(response.status) ? null : response.body;
    const outgoing = new NextResponse(body,{status:response.status,headers:{"Content-Type":response.headers.get("content-type")??"application/json","Content-Disposition":response.headers.get("content-disposition")??""}});
    if (rotated) setSessionCookies(outgoing, rotated.tokens);
    return outgoing;
  } catch (error) {
    if (error instanceof SessionError && error.status === 401) return Response.json({detail:"Your session has expired."},{status:401});
    return Response.json({detail:"The appointment service is temporarily unavailable."},{status:503});
  }
}
