import "server-only";

import type { NextRequest, NextResponse } from "next/server";

import type { AccessSummary, Session, UserSummary } from "@/lib/api/contracts";
import { djangoEndpoints } from "@/lib/api/endpoints";

const ACCESS_COOKIE = "jeevasetu_access";
const REFRESH_COOKIE = "jeevasetu_refresh";
const API_BASE_URL = process.env.DJANGO_API_BASE_URL ?? "http://localhost:8000/api/v1";
const ORGANIZATION_SLUG = process.env.NEXT_PUBLIC_DEFAULT_ORGANIZATION_SLUG ?? "";
const secureCookies = process.env.NODE_ENV === "production";
const ACCESS_COOKIE_SECONDS = 30 * 60;
const REFRESH_COOKIE_SECONDS = 8 * 60 * 60;

type TokenPair = { access: string; refresh: string; user?: UserSummary };
const refreshes = new Map<string, Promise<{ tokens: TokenPair; session: Session }>>();

export class SessionError extends Error {
  constructor(
    public status: number,
    public detail: string,
    public fieldErrors?: Record<string, string>,
  ) {
    super(detail);
  }
}

function apiUrl(path: string) {
  return `${API_BASE_URL.replace(/\/$/, "")}${path}`;
}

export function isSameOrigin(request: NextRequest) {
  const origin = request.headers.get("origin");
  if (!origin) return true;
  const protocol = request.headers.get("x-forwarded-proto") ?? request.nextUrl.protocol.slice(0, -1);
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host");
  return Boolean(host && origin === `${protocol}://${host}`);
}

export function requireSameOrigin(request: NextRequest) {
  if (!isSameOrigin(request)) throw new SessionError(403, "This request is not permitted.");
}

async function parseError(response: Response): Promise<SessionError> {
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    return new SessionError(response.status, "The service is temporarily unavailable.");
  }
  if (response.status === 429) return new SessionError(429, "Too many attempts. Please try again later.");
  if (response.status === 401) return new SessionError(401, "The credentials or session are invalid.");
  if (response.status === 403) return new SessionError(403, "Your account does not have active access.");
  if (response.status === 404) {
    return new SessionError(
      404,
      "Your account exists, but organization access has not been assigned yet. Please contact the Owner or system administrator.",
    );
  }
  const fields: Record<string, string> = {};
  if (body && typeof body === "object") {
    for (const [key, value] of Object.entries(body)) {
      if (key !== "detail") fields[key] = Array.isArray(value) ? String(value[0]) : String(value);
    }
  }
  return new SessionError(response.status, "Please review the highlighted information.", fields);
}

async function djangoFetch(path: string, init: RequestInit = {}, access?: string) {
  try {
    return await fetch(apiUrl(path), {
      ...init,
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        ...(ORGANIZATION_SLUG ? { "X-Organization-Slug": ORGANIZATION_SLUG } : {}),
        ...(access ? { Authorization: `Bearer ${access}` } : {}),
        ...init.headers,
      },
    });
  } catch {
    throw new SessionError(503, "The service is temporarily unavailable.");
  }
}

async function checkedJson<T>(response: Response): Promise<T> {
  if (!response.ok) throw await parseError(response);
  return (await response.json()) as T;
}

export async function login(payload: unknown) {
  if (!ORGANIZATION_SLUG) throw new SessionError(400, "Organization context is not configured.");
  const tokens = await checkedJson<TokenPair>(
    await djangoFetch(djangoEndpoints.login, { method: "POST", body: JSON.stringify(payload) }),
  );
  const access = await checkedJson<AccessSummary>(
    await djangoFetch(djangoEndpoints.access, {}, tokens.access),
  );
  if (!tokens.user) throw new SessionError(401, "The credentials or session are invalid.");
  return { tokens, session: { user: tokens.user, access } satisfies Session };
}

export async function publicPost<T>(path: string, payload: unknown) {
  return checkedJson<T>(
    await djangoFetch(path, { method: "POST", body: JSON.stringify(payload) }),
  );
}

async function loadSessionWithAccess(access: string): Promise<Session> {
  const [profileResponse, accessResponse] = await Promise.all([
    djangoFetch(djangoEndpoints.profile, {}, access),
    djangoFetch(djangoEndpoints.access, {}, access),
  ]);
  if (!profileResponse.ok) throw await parseError(profileResponse);
  if (!accessResponse.ok) throw await parseError(accessResponse);
  const [user, roleAccess] = (await Promise.all([
    profileResponse.json(),
    accessResponse.json(),
  ])) as [UserSummary, AccessSummary];
  return { user, access: roleAccess };
}

export function refreshSession(refresh: string) {
  const existing = refreshes.get(refresh);
  if (existing) return existing;
  const pending = (async () => {
    const tokens = await checkedJson<TokenPair>(
      await djangoFetch(djangoEndpoints.refresh, { method: "POST", body: JSON.stringify({ refresh }) }),
    );
    return { tokens, session: await loadSessionWithAccess(tokens.access) };
  })().finally(() => refreshes.delete(refresh));
  refreshes.set(refresh, pending);
  return pending;
}

export async function currentSession(request: NextRequest) {
  const access = request.cookies.get(ACCESS_COOKIE)?.value;
  const refresh = request.cookies.get(REFRESH_COOKIE)?.value;
  if (!access || !refresh) throw new SessionError(401, "Your session has expired.");
  try {
    return { session: await loadSessionWithAccess(access), tokens: null };
  } catch (error) {
    if (!(error instanceof SessionError) || error.status !== 401) throw error;
    return refreshSession(refresh);
  }
}

export async function updateProfile(request: NextRequest, payload: unknown) {
  const current = await currentSession(request);
  const access = current.tokens?.access ?? request.cookies.get(ACCESS_COOKIE)?.value;
  const response = await djangoFetch(
    djangoEndpoints.profile,
    { method: "PATCH", body: JSON.stringify(payload) },
    access,
  );
  return { user: await checkedJson<UserSummary>(response), tokens: current.tokens };
}

export async function revokeSession(request: NextRequest) {
  const access = request.cookies.get(ACCESS_COOKIE)?.value;
  const refresh = request.cookies.get(REFRESH_COOKIE)?.value;
  if (access && refresh) {
    await djangoFetch(
      djangoEndpoints.logout,
      { method: "POST", body: JSON.stringify({ refresh }) },
      access,
    );
  }
}

export function setSessionCookies(response: NextResponse, tokens: TokenPair) {
  response.cookies.set(ACCESS_COOKIE, tokens.access, {
    httpOnly: true,
    secure: secureCookies,
    sameSite: "lax",
    path: "/",
    maxAge: ACCESS_COOKIE_SECONDS,
  });
  response.cookies.set(REFRESH_COOKIE, tokens.refresh, {
    httpOnly: true,
    secure: secureCookies,
    sameSite: "lax",
    path: "/",
    maxAge: REFRESH_COOKIE_SECONDS,
  });
}

export function clearSessionCookies(response: NextResponse) {
  response.cookies.set(ACCESS_COOKIE, "", { httpOnly: true, path: "/", maxAge: 0 });
  response.cookies.set(REFRESH_COOKIE, "", { httpOnly: true, path: "/", maxAge: 0 });
}
