// @vitest-environment node
import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

describe("practitioner API session continuity", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("refreshes and retries once when an applicant access token expires", async () => {
    const responses = [
      new Response(JSON.stringify({ detail:"expired" }), { status:401 }),
      new Response(JSON.stringify({ access:"new-access", refresh:"new-refresh" }), { status:200 }),
      new Response(JSON.stringify({ id:"user", first_name:"A", last_name:"Applicant", email:"a@example.com", mobile_number:null, profile_image:"", roles:[] }), { status:200 }),
      new Response(JSON.stringify({ user_id:"user", organization:{ id:"org", slug:"jeevasetu" }, permitted_clinics:[], roles:[] }), { status:200 }),
      new Response(JSON.stringify([{ id:"draft", status:"DRAFT" }]), { status:200 }),
    ];
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => responses.shift()!);
    const { practitionerApi } = await import("./server-api");
    const request = new NextRequest("http://localhost/api/practitioners/me", { headers:{ cookie:"jeevasetu_access=expired; jeevasetu_refresh=valid" } });

    const response = await practitionerApi(request, "/practitioners/applications/me/");

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(5);
    expect(response.headers.get("set-cookie")).toContain("jeevasetu_access=new-access");
  });

  it("returns a real expiry when refresh is invalid", async () => {
    const responses = [
      new Response(JSON.stringify({ detail:"expired" }), { status:401 }),
      new Response(JSON.stringify({ detail:"invalid" }), { status:401 }),
    ];
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => responses.shift()!);
    const { practitionerApi } = await import("./server-api");
    const request = new NextRequest("http://localhost/api/practitioners/me", { headers:{ cookie:"jeevasetu_access=expired; jeevasetu_refresh=invalid" } });
    const response = await practitionerApi(request, "/practitioners/applications/me/");
    expect(response.status).toBe(401);
  });
  it("streams a private PDF after transparent refresh", async () => {
    const responses = [
      new Response(JSON.stringify({ access:"pdf-access", refresh:"pdf-refresh" }), { status:200 }),
      new Response(JSON.stringify({ id:"user", first_name:"A", last_name:"Applicant", email:"a@example.com", mobile_number:null, profile_image:"", roles:[] }), { status:200 }),
      new Response(JSON.stringify({ user_id:"user", organization:{ id:"org", slug:"jeevasetu" }, permitted_clinics:[], roles:[] }), { status:200 }),
      new Response("%PDF-1.4 government", { status:200, headers:{"Content-Type":"application/pdf"} }),
    ];
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => responses.shift()!);
    const { practitionerApi } = await import("./server-api");
    const request = new NextRequest("http://localhost/api/practitioners/documents/document-1", { headers:{ cookie:"jeevasetu_refresh=pdf-valid" } });
    const response = await practitionerApi(request, "/practitioners/documents/document-1/");
    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("application/pdf");
    expect(await response.text()).toBe("%PDF-1.4 government");
    expect(response.headers.get("set-cookie")).toContain("jeevasetu_access=pdf-access");
  });

  it("proxies document deletion with an empty 204 response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status:204 }));
    const { practitionerApi } = await import("./server-api");
    const request = new NextRequest("http://localhost/api/practitioners/documents/document-1", { headers:{ cookie:"jeevasetu_access=valid; jeevasetu_refresh=valid" } });
    const response = await practitionerApi(request, "/practitioners/documents/document-1/", { method:"DELETE" });
    expect(response.status).toBe(204);
    expect(await response.text()).toBe("");
  });
});
