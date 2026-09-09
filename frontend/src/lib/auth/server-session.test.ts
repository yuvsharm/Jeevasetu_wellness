// @vitest-environment node
import { NextRequest, NextResponse } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

const user = { id: "user", first_name: "A", last_name: "User", email: "a@example.com", mobile_number: null, profile_image: "", roles: ["CUSTOMER"] };
const access = { user_id: "user", organization: { id: "org", slug: "jeevasetu" }, permitted_clinics: [], roles: [{ id: "role", user_id: "user", organization_id: "org", clinic_id: null, role: "CUSTOMER", scope: "organization", is_active: true }] };

describe("server session", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("rotates a refresh token server-side after access expiry", async () => {
    const responses = [
      new Response(JSON.stringify({ detail: "expired" }), { status: 401 }),
      new Response(JSON.stringify({ detail: "expired" }), { status: 401 }),
      new Response(JSON.stringify({ access: "new-access", refresh: "new-refresh" }), { status: 200 }),
      new Response(JSON.stringify(user), { status: 200 }),
      new Response(JSON.stringify(access), { status: 200 }),
    ];
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => responses.shift()!);
    const { currentSession } = await import("./server-session");
    const request = new NextRequest("http://localhost/api/session/me", { headers: { cookie: "jeevasetu_access=old; jeevasetu_refresh=rotate" } });

    const result = await currentSession(request);

    expect(result.tokens).toMatchObject({ access: "new-access", refresh: "new-refresh" });
    expect(result.session.access.roles[0].role).toBe("CUSTOMER");
  });

  it("rotates a valid refresh when the browser removed the access cookie", async () => {
    const responses = [
      new Response(JSON.stringify({ access: "renewed-access", refresh: "renewed-refresh" }), { status: 200 }),
      new Response(JSON.stringify(user), { status: 200 }),
      new Response(JSON.stringify(access), { status: 200 }),
    ];
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => responses.shift()!);
    const { currentSession } = await import("./server-session");
    const request = new NextRequest("http://localhost/api/session/me", { headers: { cookie: "jeevasetu_refresh=retained-refresh" } });
    const result = await currentSession(request);
    expect(result.tokens).toMatchObject({ access: "renewed-access", refresh: "renewed-refresh" });
  });

  it("rejects when both session cookies are missing", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    const { currentSession } = await import("./server-session");
    await expect(currentSession(new NextRequest("http://localhost/api/session/me"))).rejects.toEqual(expect.objectContaining({ status: 401 }));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects an expired or revoked refresh session safely", async () => {
    const responses = [
      new Response(JSON.stringify({ detail: "expired" }), { status: 401 }),
      new Response(JSON.stringify({ detail: "expired" }), { status: 401 }),
      new Response(JSON.stringify({ detail: "invalid" }), { status: 401 }),
    ];
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => responses.shift()!);
    const { currentSession } = await import("./server-session");
    const request = new NextRequest("http://localhost/api/session/me", { headers: { cookie: "jeevasetu_access=old; jeevasetu_refresh=revoked" } });

    await expect(currentSession(request)).rejects.toEqual(expect.objectContaining({ status: 401 }));
  });

  it("rejects cross-origin unsafe requests", async () => {
    const { requireSameOrigin, SessionError } = await import("./server-session");
    const request = new NextRequest("http://localhost/api/session/login", { headers: { host: "localhost", origin: "https://attacker.example" } });
    expect(() => requireSameOrigin(request)).toThrow(SessionError);
  });

  it("deduplicates concurrent refresh rotation for the same token", async () => {
    const responses = [
      new Response(JSON.stringify({ access: "shared-access", refresh: "shared-refresh" }), { status: 200 }),
      new Response(JSON.stringify(user), { status: 200 }),
      new Response(JSON.stringify(access), { status: 200 }),
    ];
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => responses.shift()!);
    const { refreshSession } = await import("./server-session");

    const [first, second] = await Promise.all([
      refreshSession("same-rotating-token"),
      refreshSession("same-rotating-token"),
    ]);

    expect(first.tokens.refresh).toBe("shared-refresh");
    expect(second.tokens.refresh).toBe("shared-refresh");
    expect((await refreshSession("same-rotating-token")).tokens.refresh).toBe("shared-refresh");
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("establishes an applicant session without an operational role", async () => {
    const applicant = { ...user, roles: [] };
    const applicantAccess = { ...access, roles: [] };
    const responses = [
      new Response(JSON.stringify({ access: "applicant-access", refresh: "applicant-refresh", user: applicant }), { status: 200 }),
      new Response(JSON.stringify(applicantAccess), { status: 200 }),
    ];
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => responses.shift()!);
    const { login } = await import("./server-session");

    const result = await login({ identifier: "applicant@example.com", password: "StrongPassword42" });

    expect(result.session.access.roles).toEqual([]);
  });

  it("explains when organization access has not been assigned", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "Not found." }), { status: 404 }),
    );
    const { login } = await import("./server-session");

    await expect(login({ identifier: "owner@example.com", password: "not-logged" })).rejects.toEqual(
      expect.objectContaining({
        status: 404,
        detail: expect.stringMatching(/organization access has not been assigned yet/i),
      }),
    );
  });

  it("uses the customer-only password endpoint", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/auth/customer-login/")) return new Response(JSON.stringify({ access: "customer-access", refresh: "customer-refresh", refresh_max_age: 604800, user }), { status: 200 });
      return new Response(JSON.stringify(access), { status: 200 });
    });
    const { customerPasswordLogin } = await import("./server-session");
    const result = await customerPasswordLogin({ mobile_number: "9876543210", password: "secret" });
    expect(result.tokens.refresh_max_age).toBe(604800);
    expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith("/auth/customer-otp-login/"))).toBe(false);
  });

  it("applies the backend-provided customer refresh lifetime to the secure cookie", async () => {
    const { setSessionCookies } = await import("./server-session");
    const response = NextResponse.json({});
    setSessionCookies(response, { access: "access", refresh: "refresh", refresh_max_age: 604800 });
    expect(response.cookies.get("jeevasetu_refresh")?.value).toBe("refresh");
    expect(response.headers.get("set-cookie")).toContain("Max-Age=604800");
  });

  it("preserves customer registration retry timing from Django", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "Request was throttled.", retry_after: 601 }), {
        status: 429,
        headers: { "Retry-After": "601" },
      }),
    );
    const { customerRegister } = await import("./server-session");
    await expect(customerRegister({})).rejects.toEqual(expect.objectContaining({
      status: 429,
      retryAfter: 601,
      detail: "Too many registration attempts. Please try again in 11 minutes.",
    }));
  });

  it("promotes meaningful registration field errors instead of numeric keys", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ mobile_number: ["This mobile number is already registered. Please sign in."] }), { status: 400 }),
    );
    const { customerRegister } = await import("./server-session");
    await expect(customerRegister({})).rejects.toEqual(expect.objectContaining({
      status: 400,
      detail: "This mobile number is already registered. Please sign in.",
      fieldErrors: { mobile_number: "This mobile number is already registered. Please sign in." },
    }));
  });

  it("forwards the exact signed registration proof and field name to Django", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      if (String(input).endsWith("/auth/customer-register/")) {
        return new Response(JSON.stringify({ access: "customer-access", refresh: "customer-refresh", user }), { status: 201 });
      }
      return new Response(JSON.stringify(access), { status: 200 });
    });
    const { customerRegister } = await import("./server-session");
    await customerRegister({ booking_verification_token: "exact-signed-proof", mobile_number: "9876543210" });
    const registrationCall = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/auth/customer-register/"));
    expect(JSON.parse(String(registrationCall?.[1]?.body))).toEqual({
      booking_verification_token: "exact-signed-proof",
      mobile_number: "9876543210",
    });
  });

  it("treats legacy list validation responses as detail rather than field zero", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(["Please verify your mobile number again."]), { status: 400 }),
    );
    const { customerRegister } = await import("./server-session");
    await expect(customerRegister({})).rejects.toEqual(expect.objectContaining({
      detail: "Please verify your mobile number again.",
      fieldErrors: undefined,
    }));
  });

  it("preserves safe password reset validation details from Django", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ new_password: ["This password is too common."] }), { status: 400 }),
    );
    const { customerPasswordReset } = await import("./server-session");
    await expect(customerPasswordReset({})).rejects.toEqual(expect.objectContaining({
      status: 400,
      detail: "This password is too common.",
      fieldErrors: { new_password: "This password is too common." },
    }));
  });
});
