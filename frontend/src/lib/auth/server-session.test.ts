// @vitest-environment node
import { NextRequest } from "next/server";
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
});
